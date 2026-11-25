# D1AB2 Minikube evidence

Run date: 2026-11-21. Kubernetes context: `minikube`; namespace: `rahbar`.

## Results

- Batch A initial ingest: 3/3 documents passed; 11 chunks indexed.
- Unchanged Batch A rerun: 0 chunks embedded, 11 reused.
- Planted Batch B: 9 passed, 4 rejected and quarantined. The failures were truncated text, a near duplicate, an exact duplicate, and missing version metadata.
- Clean Batch B lifecycle update: 8/8 passed; 6 added, 1 changed, 1 unchanged, and 1 deleted. It embedded 13 chunks and reused 4.
- The update retained the 2023 and 2026 rule editions as superseded and made the 2027 edition the newest active version.
- The restore Job completed and returned the experiment's active pointer to its Batch A collection. This run used an isolated `rahbar-a03-d1ab2-*` collection prefix.

## Files

- `terminal.txt`: complete output from the run, including Job status and restore.
- `batch-a-first-report.json`, `batch-a-repeat-report.json`, `batch-b-rejected-report.json`, `batch-b-clean-report.json`: saved verifier reports.
- `quarantine-batch-b/`: the four rejected source files copied from the persistent quarantine volume.

Reproduce from the repository root with `pwsh docs/evidence/run-d1ab2.ps1` after Minikube and the `rahbar` namespace are available. The script builds from the local `rahbar-indexer:d1ab2` image created for this task.
