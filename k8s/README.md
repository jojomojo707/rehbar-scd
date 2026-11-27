# Kubernetes: from a fresh cluster to a working RAGOps pipeline

Everything runs in namespace `rahbar` on minikube. `kubectl apply -k k8s/overlays/dev` creates
the whole platform; the Jobs in this folder (not in the kustomization) are started on demand.

## Objects and their RAGOps responsibility

| Object | Kind | Responsibility |
| --- | --- | --- |
| `api` | Deployment (3 replicas, RollingUpdate `maxSurge 1`, `maxUnavailable 0`) + Service + HPA | Query pipeline; reads the index only; writes one JSON trace per query to stdout and to the PVC |
| `api-candidate` | Deployment + Service | Serves the candidate collection `rahbar-candidate-*`; reachable only from evaluation pods (NetworkPolicy) |
| `chroma` | StatefulSet + PVC `data-chroma-0` | Vector store |
| `indexer` | Job | Ingest + verify + update data lake + update retrieval sources (Part A). **The only Chroma writer** (indexer image, service account `rahbar-indexer`) |
| `reindex` | CronJob (Sun 03:00) | Re-runs the same ingestion spec on a schedule (`scripts/check_manifests.py` keeps the two identical) |
| `candidate-ingest` | Job (`k8s/candidate-ingest-job.yaml`) | Builds the candidate collection from the same lake, with `rahbar-candidate-config` |
| `eval` | Job (`k8s/eval-job.yaml`) | Part B suite against the API in ConfigMap `eval-target`; release gate; exits 1 on REJECT |
| `gate` | Job (`k8s/gate-job.yaml`) | Re-applies the gate to the latest candidate result with the current thresholds |
| `pipeline-data` | PVC (2Gi) | Data lake `lake/`, `inbox/`, `quarantine/`, `archive/`, `eval/results/`, `eval/baseline/`, `traces/` |
| `corpus` | PVC (1Gi) | Downloaded source corpus (Batch A), filled by the indexer's `fetch-corpus` init container |
| `rahbar-config` | ConfigMap | Runtime settings shared by API and indexer (embedding pin, chunking, top-k...) |
| `rahbar-candidate-config` | ConfigMap | Candidate overrides: `CHROMA_COLLECTION=rahbar-candidate`, `CHUNK_SIZE=384` |
| `release-gate-thresholds` | ConfigMap | Gate thresholds, mounted at `/gate` (edit, rerun, no rebuild) |
| `eval-target` | ConfigMap | Which API the eval Job tests and with which label |
| `ingest-batch` | ConfigMap (optional, you create it) | A new batch of documents for the ingestion Job (`/batch`) |
| `rahbar-secret` | Secret (from `make secret`) | `LLM_API_KEY` for the API and the faithfulness judge |

## Fresh cluster, in order

Prerequisites: Docker, minikube, kubectl, and the Groq key in your shell (`export LLM_API_KEY=...`).

```bash
make cluster                     # minikube start (7 GB, 4 CPUs) + ingress + metrics-server
make images                      # build api, indexer, evaluator, ui and load them into minikube
kubectl apply -f k8s/base/namespace.yaml
make secret                      # creates rahbar-secret from $LLM_API_KEY (never from a file)
kubectl apply -k k8s/overlays/dev
kubectl -n rahbar wait --for=condition=complete --timeout=60m job/indexer   # Batch A ingest
kubectl -n rahbar rollout status deployment/api --timeout=10m
kubectl -n rahbar get all,pvc,configmap,cronjob,job
```

## Part A: ingest a batch (also the demo's "unseen documents")

```bash
kubectl -n rahbar create configmap ingest-batch --from-file=eval/batches/batch-b   # any folder
kubectl -n rahbar delete job indexer --ignore-not-found
kubectl apply -k k8s/overlays/dev            # re-creates Job indexer, which reads /batch
kubectl -n rahbar wait --for=condition=complete --timeout=30m job/indexer
kubectl -n rahbar logs job/indexer -c indexer                # pass/fail table per check
# unchanged rerun: delete the Job and apply again -> "embedded_chunks": 0
kubectl -n rahbar run counts --rm -i --restart=Never --image=rahbar-indexer:dev \
  --overrides='{"spec":{"enableServiceLinks":false}}' --env=CHROMA_HOST=chroma \
  --env=CHROMA_PORT=8000 --labels=app.kubernetes.io/name=indexer \
  --command -- python -m pipeline.counts --source fees-2026.md        # orphan check
```

### Unseen documents larger than a ConfigMap (the usual case for PDFs)

A ConfigMap holds at most 1 MiB, about 750 KB of PDF after base64, and real FAST PDFs are 1-15 MB.
`kubectl create configmap` then fails with `Too long: may not be more than 1048576 bytes`. Copy
the folder onto the `pipeline-data` PVC instead. The indexer Job and CronJob read every folder
under `/pipeline-data/incoming/` as one batch:

```bash
mkdir demo-batch && cp ~/Downloads/*.pdf demo-batch/
# Give each PDF its title and version; a file without them is quarantined (completeness check).
cat > demo-batch/_index.json <<'EOF'
[{"file": "exam-notice.pdf", "title": "Final exam notice", "doc_version": "2026-11"}]
EOF
scripts/upload_batch.sh demo-batch                  # short-lived pod + kubectl cp, no rebuild
kubectl -n rahbar delete job indexer --ignore-not-found
kubectl apply -k k8s/overlays/dev
kubectl -n rahbar wait --for=condition=complete --timeout=30m job/indexer
kubectl -n rahbar logs job/indexer -c indexer      # pass/fail per check for each new file
scripts/trace_probe.sh "a question about the new document"   # trace shows the new collection
scripts/upload_batch.sh --remove demo-batch         # optional: stop later runs re-reading it
```

A file that `_index.json` does not list is still verified, and is quarantined with "missing
title; missing date/version". If you fix its metadata (add it to `_index.json`) and upload again,
the next run verifies it again. The same bytes with the same metadata stay quarantined. A
rehearsal with two real PDFs (2.6 MB) is in
`docs/evidence/a03/A-unseen-batch-pvc-rehearsal.txt`.

Restore an archived version, or delete a batch document, with the same image:
`python -m pipeline.run --restore-version <file>` / `--delete <file>` (see the README).

## Demo: run the evaluation as a Job

`kubectl apply -k k8s/overlays/dev` (used for every ingestion above) resets ConfigMap `eval-target`
to its committed values: 2 runs against `api-candidate`, and the gate thresholds to theirs. So
patch it right before the eval Job. Use 1 run: 47 questions x 2 runs need about 260k tokens, over
the free tier's 200k per day. Do not use the label `baseline` at the demo: that label overwrites
the stored baseline the gate compares against.

```bash
kubectl -n rahbar patch configmap eval-target --type merge \
  -p '{"data":{"EVAL_API_URL":"http://api:8000","EVAL_LABEL":"demo","EVAL_RUNS":"1"}}'
kubectl -n rahbar delete job eval --ignore-not-found && kubectl apply -f k8s/eval-job.yaml
kubectl -n rahbar wait --for=condition=complete --timeout=60m job/eval   # about 18 minutes
kubectl -n rahbar logs job/eval | sed -n '/^# Part B suite/,$p'          # 3 levels + gate result
```

## Parts B, C, F3: baseline, candidate, gate, release, undo

```bash
# baseline = the live API
kubectl -n rahbar patch configmap eval-target --type merge \
  -p '{"data":{"EVAL_API_URL":"http://api:8000","EVAL_LABEL":"baseline"}}'
kubectl -n rahbar delete job eval --ignore-not-found && kubectl apply -f k8s/eval-job.yaml
# candidate = its own collection
kubectl apply -f k8s/candidate-ingest-job.yaml
kubectl -n rahbar rollout restart deployment/api-candidate
kubectl -n rahbar patch configmap eval-target --type merge \
  -p '{"data":{"EVAL_API_URL":"http://api-candidate:8000","EVAL_LABEL":"candidate"}}'
kubectl -n rahbar delete job eval --ignore-not-found && kubectl apply -f k8s/eval-job.yaml
kubectl -n rahbar logs job/eval | tail -40          # summary table + RELEASE GATE: PASS/REJECT
# threshold change without a rebuild
kubectl -n rahbar edit configmap release-gate-thresholds
kubectl -n rahbar delete job gate --ignore-not-found && kubectl apply -f k8s/gate-job.yaml
# release a passing candidate, watch it, undo a bad release
kubectl -n rahbar set env deployment/api CHROMA_COLLECTION=rahbar-candidate
kubectl -n rahbar rollout status deployment/api --timeout=10m
kubectl -n rahbar rollout undo deployment/api
```

## Part D, F4: traces and metrics

```bash
kubectl -n rahbar logs deploy/api | grep '"query trace"' | tail -1      # stdout JSON line
kubectl -n rahbar cp <api-pod>:/pipeline-data/traces traces/run-x      # the PVC copy
python eval/trace.py trace <trace-id> --trace-dir traces/run-x
python eval/trace.py summary --since <iso> --until <iso> --trace-dir traces/run-x
kubectl -n rahbar port-forward svc/api 8000:8000 & curl -s localhost:8000/metrics | grep rahbar_
```

## Storage notes

`pipeline-data` is ReadWriteOnce on the single minikube node. The init container
`prepare-pipeline-data` creates the directories as UID/GID 10001 and checks they are writable;
`fsGroup: 10001` gives the non-root workloads group access. Ingestion Jobs share the lake
manifest, so run them one at a time (`concurrencyPolicy: Forbid` on the CronJob).
