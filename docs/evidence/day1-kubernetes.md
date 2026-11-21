# Assignment 03 Day 1 Minikube evidence

- Context: `minikube`, API Deployment rolled out with the PVC mount and tracing code.
- New `pipeline-data` PVC: Bound, 2Gi, ReadWriteOnce; the existing corpus, Chroma and Redis PVCs remain bound.
- Permission Job `pipeline-data-permission-probe`: completed as UID/GID 10001 and created quarantine, archive, eval/results and traces paths.
- A live API injection query produced a full trace on the PVC and a structured `query trace` line in `kubectl logs`.
- The trace survived deletion/recreation of its API pod. After restart, `/readyz` returned `ready` and `/metrics` returned HTTP 200.
- The first base `indexer` Job attempt used the previously cached `rahbar-indexer:dev` image, which lacked `pipeline.prepare_data`, and hit its backoff limit. The image tag was updated from the built `d1day1` image, and the standalone permission Job passed. The data-changing indexer Job was not rerun so the existing Chroma collection would remain intact during evaluation.

See `day1-traces/` for JSONL files, prompt reconstruction, stdout capture, before/after restart checks, readiness and metrics responses.
