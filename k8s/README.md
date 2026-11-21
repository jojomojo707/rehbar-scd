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
