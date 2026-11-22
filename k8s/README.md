# Kubernetes storage and Day 1 commands

The existing `corpus` PVC holds the source corpus. The separate `pipeline-data` PVC holds:

| Pod path | Purpose | Writer |
| --- | --- | --- |
| `/pipeline-data/quarantine/` | Rejected source documents by ingest run | Indexer Job/CronJob |
| `/pipeline-data/archive/` | Reserved for archived prior source/version material | Indexer Job/CronJob |
| `/pipeline-data/eval/results/` | Verification and evaluation JSON results | Indexer and evaluation Jobs |
| `/pipeline-data/traces/` | Request trace JSONL (`TRACE_DIR`) | API pods |

An init container runs as UID/GID 10001 and creates each directory plus a temporary write probe.
`fsGroup: 10001` and `fsGroupChangePolicy: OnRootMismatch` provide group access to non-root
workloads. Chroma keeps its existing `data-chroma-0` PVC. This claim requests 2 GiB with
`ReadWriteOnce` for the single-node Minikube cluster. Multi-node API placement needs an RWX
storage class or per-replica trace claims.

## Assignment 03 Day 1 commands

From the repository root, with Docker and Minikube running:

```powershell
kubectl config current-context
kubectl apply -k k8s/overlays/dev
kubectl -n rahbar wait --for=condition=Ready pod -l app=api --timeout=240s
kubectl -n rahbar exec deploy/api -- sh -c 'test -w /pipeline-data/traces && echo trace-volume-writable'
kubectl -n rahbar port-forward svc/api 8000:8000
```

In another terminal:

```powershell
python eval/run_suite.py --api http://127.0.0.1:8000 --seed 20261121 --pause 1
python eval/trace.py summary --trace-dir traces
python eval/trace.py trace <request-id> --trace-dir traces
```

`run_suite.py` exits 0 when both runs complete, 2 on a CLI/run error. Each underlying
`run_eval.py` result reports the rubric gate: 0 pass, 1 metric-gate failure, 2 invalid input.
The suite writes timestamped per-question JSON and a difference table. Sequential repetitions
may be semantic-cache hits; inspect each row's `cached` value before comparing latency.

## Initial Job resource estimates

The Day 1 baseline passed the indexer suite (42 passed, 1 skipped); live API pods settled at
245–272 MiB after cold model load. These are starting estimates, not tuned full-suite peaks:

| Job | Request | Limit | Basis |
| --- | --- | --- | --- |
| Indexer | 500m CPU, 2200Mi | 2 CPU, 3Gi | Existing model-loaded ingestion Job |
| Evaluation | 500m CPU, 1Gi | 2 CPU, 3Gi | CPU embedder and HTTP result accumulation |
| Data-path init | 50m CPU, 64Mi | 200m CPU, 256Mi | Directory creation and write probes |

Record actual peak usage with the full Day 2 evaluation Job before describing estimates as tuned.

## Assignment 03 Day 2: evaluation, gate, candidate, and undo

The `evaluation` CronJob is a reproducible Job template; create a named Job when needed. Its
evaluator image is built and loaded by `make images`. It calls the candidate Service, writes the
timestamped API JSON under `/pipeline-data/eval/results/`, then calls `release_gate.py` with the
baseline, manual faithfulness review, and mounted ConfigMap thresholds. A rejected candidate exits
1 and is not promoted. Gate thresholds can be edited on the ConfigMap and re-read on each new Job.

```powershell
make images
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -k k8s/overlays/dev
kubectl -n rahbar rollout status deployment/api-candidate --timeout=10m
kubectl -n rahbar create job --from=cronjob/evaluation eval-candidate-1
kubectl -n rahbar wait --for=condition=complete job/eval-candidate-1 --timeout=2h
kubectl -n rahbar logs job/eval-candidate-1
```

To show a ConfigMap edit changing the decision without rebuilding, temporarily change
`MAX_RECALL5_DROP`, rerun the Job under a new name, and restore the committed value (`0.05`). Save
both complete outputs. Promote only a passing candidate and demonstrate its guarded rollout and
rollback:

```powershell
kubectl -n rahbar set env deployment/api TOP_K=7
kubectl -n rahbar rollout status deployment/api --timeout=10m
kubectl -n rahbar rollout undo deployment/api
kubectl -n rahbar rollout status deployment/api --timeout=10m
```

`api-candidate` is separate; NetworkPolicies allow only the evaluation workload to reach it. It
uses the same embedding pin and active Chroma collection but overrides `TOP_K` to 7. The normal
API Deployment retains rolling `maxUnavailable: 0`. For a controlled comparison, save baseline and
candidate runs from the same cluster, collection, corpus and suite; do not present the older Day 1
results as a controlled comparison.

### Batch B drift run

Create the input ConfigMap from the committed, verified subset, then explicitly create the suspended
CronJob template. The Job writes into an isolated collection named `rahbar-day2-batch-b`; it cannot
replace the collection used by the live API.

```powershell
kubectl create configmap batch-b-clean --from-file=eval/batches/batch-b-clean -n rahbar `
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n rahbar create job --from=cronjob/batch-b-ingest batch-b-drift-1
kubectl -n rahbar wait --for=condition=complete job/batch-b-drift-1 --timeout=30m
kubectl -n rahbar logs job/batch-b-drift-1
```

To evaluate the isolated collection, update `rahbar-candidate-config` with
`CHROMA_COLLECTION=rahbar-day2-batch-b`, restart `api-candidate`, and create an evaluation Job.
Then restore the ConfigMap from `k8s/base/candidate-configmap.yaml` and restart the candidate again.
Compare module metrics (embedding/model unchanged), component retrieval metrics and end-to-end
metrics; the Batch B only collection is a deliberate data drift condition, not a production release.
