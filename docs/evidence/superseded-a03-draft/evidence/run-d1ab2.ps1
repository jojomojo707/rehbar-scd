$ErrorActionPreference = "Stop"
$namespace = "rahbar"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Set-Location $repoRoot
$template = Join-Path $PSScriptRoot "d1ab2-indexer-job.template.yaml"
$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$evidenceDir = Join-Path $PSScriptRoot "d1ab2-$runId"
$terminal = Join-Path $evidenceDir "terminal.txt"
New-Item -ItemType Directory -Force $evidenceDir | Out-Null

function Record([string]$text) {
    $text | Tee-Object -FilePath $terminal -Append
}

function Run-Kubectl([string[]]$arguments) {
    $result = & kubectl @arguments 2>&1
    $result | ForEach-Object { Record ([string]$_) }
    if ($LASTEXITCODE -ne 0) {
        throw "kubectl $($arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
    return $result
}

function Run-IndexerJob([string]$label, [string]$configMap, [bool]$expectFailure = $false,
                        [bool]$restore = $false) {
    $jobName = "d1ab2-$label-$runId".ToLowerInvariant()
    $argsYaml = if ($restore) { '["--restore"]' } else { "[]" }
    $collection = "rahbar-a03-d1ab2-$runId"
    $yaml = (Get-Content -LiteralPath $template -Raw).Replace("__JOB_NAME__", $jobName).Replace(
        "__CONFIGMAP__", $configMap).Replace("__ARGS__", $argsYaml).Replace(
        "__COLLECTION__", $collection).Replace("__RUN_ID__", $runId)
    $manifest = Join-Path $env:TEMP "$jobName.yaml"
    Set-Content -LiteralPath $manifest -Value $yaml -Encoding utf8

    Record "===== $label : kubectl apply job/$jobName ====="
    Run-Kubectl @("apply", "-f", $manifest) | Out-Null
    $condition = if ($expectFailure) { "failed" } else { "complete" }
    Run-Kubectl @("wait", "--for=condition=$condition", "job/$jobName", "-n", $namespace,
                  "--timeout=20m") | Out-Null
    Run-Kubectl @("get", "job/$jobName", "-n", $namespace, "-o", "wide") | Out-Null

    $pod = (& kubectl get pods -n $namespace -l "job-name=$jobName" `
            -o "jsonpath={.items[0].metadata.name}").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $pod) { throw "Could not find pod for $jobName" }
    $logLines = & kubectl logs -n $namespace "job/$jobName" -c indexer 2>&1
    $logLines | ForEach-Object { Record ([string]$_) }
    if ($restore) { return }

    $reportLine = $logLines | Where-Object { $_ -match '"msg": "verification report written"' } |
        Select-Object -First 1
    if (-not $reportLine) { throw "No verification report log found for $jobName" }
    $runReport = $reportLine | ConvertFrom-Json
    $reportName = if ($expectFailure) { "batch-b-rejected-report.json" }
                  elseif ($label -like "*batch-a-first*") { "batch-a-first-report.json" }
                  elseif ($label -like "*batch-a-repeat*") { "batch-a-repeat-report.json" }
                  else { "batch-b-clean-report.json" }
    $reportOut = "docs/evidence/d1ab2-$runId/$reportName"
    $remoteReport = "{0}/d1ab2-artifact-reader:/evidence/d1ab2/reports/{1}.json" -f `
        $namespace, $runReport.run_id
    Run-Kubectl @("cp", $remoteReport, $reportOut) | Out-Null
    if ($expectFailure) {
        $quarantineOut = "docs/evidence/d1ab2-$runId/quarantine-batch-b"
        New-Item -ItemType Directory -Force $quarantineOut | Out-Null
        $remoteQuarantine = "{0}/d1ab2-artifact-reader:/evidence/d1ab2/quarantine/{1}" -f `
            $namespace, $runReport.run_id
        Run-Kubectl @("cp", $remoteQuarantine, $quarantineOut) | Out-Null
    }
}

Record "Assignment 03 D1AB2 run: $runId"
Record "Context: $(kubectl config current-context)"
Run-Kubectl @("get", "nodes", "-o", "wide") | Out-Null
Run-Kubectl @("get", "pods", "-n", $namespace, "-o", "wide") | Out-Null
Run-Kubectl @("apply", "-f", (Join-Path $PSScriptRoot "d1ab2-artifact-reader.yaml")) | Out-Null
Run-Kubectl @("wait", "--for=condition=Ready", "pod/d1ab2-artifact-reader", "-n", $namespace,
              "--timeout=5m") | Out-Null

foreach ($batch in @(
    @{ name = "assignment3-batch-a"; path = "eval/batches/batch-a" },
    @{ name = "assignment3-batch-b"; path = "eval/batches/batch-b" },
    @{ name = "assignment3-batch-b-clean"; path = "eval/batches/batch-b-clean" }
)) {
    $fromFile = "--from-file=$($batch.path)"
    $config = & kubectl create configmap $batch.name -n $namespace $fromFile `
        --dry-run=client -o yaml
    if ($LASTEXITCODE -ne 0) { throw "Could not generate ConfigMap $($batch.name)" }
    $config | & kubectl apply -f - | ForEach-Object { Record ([string]$_) }
    if ($LASTEXITCODE -ne 0) { throw "Could not apply ConfigMap $($batch.name)" }
}

Run-IndexerJob "batch-a-first" "assignment3-batch-a"
Run-IndexerJob "batch-a-repeat" "assignment3-batch-a"
Run-IndexerJob "batch-b-rejected" "assignment3-batch-b" $true
Run-IndexerJob "batch-b-clean-update" "assignment3-batch-b-clean"
Run-IndexerJob "restore" "assignment3-batch-a" $false $true

Record "===== Final Job status ====="
Run-Kubectl @("get", "jobs", "-n", $namespace, "-l",
              "assignment=a03-d1ab2,assignment-run=$runId", "-o", "wide") | Out-Null
Run-Kubectl @("delete", "pod/d1ab2-artifact-reader", "-n", $namespace) | Out-Null
Record "Run artifacts: $evidenceDir"
Write-Output $evidenceDir
