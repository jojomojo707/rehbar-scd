#!/usr/bin/env bash
# Wait until a Kubernetes Job succeeds, and fail fast if it fails.
#
# Usage: scripts/wait_job.sh <job-name> <namespace> <timeout-seconds>
#
# `kubectl wait --for=condition=complete` alone would sit out the whole timeout when the Job
# fails, so this polls both outcomes. Exit 0 = Complete, 1 = Failed or timed out.
set -euo pipefail

job="${1:?usage: wait_job.sh <job> <namespace> <timeout-seconds>}"
namespace="${2:?namespace}"
timeout="${3:?timeout-seconds}"
deadline=$(( $(date +%s) + timeout ))

while (( $(date +%s) < deadline )); do
  complete="$(kubectl get job "$job" -n "$namespace" \
    -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}' 2>/dev/null || true)"
  failed="$(kubectl get job "$job" -n "$namespace" \
    -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}' 2>/dev/null || true)"
  if [[ "$complete" == "True" ]]; then
    echo "job/$job is Complete"
    kubectl logs "job/$job" -n "$namespace" --tail=20 || true
    exit 0
  fi
  if [[ "$failed" == "True" ]]; then
    echo "ERROR: job/$job Failed" >&2
    exit 1
  fi
  sleep 10
done

echo "ERROR: job/$job did not finish within ${timeout}s" >&2
exit 1
