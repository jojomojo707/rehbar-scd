#!/usr/bin/env bash
# Copy a folder of new documents onto the pipeline-data PVC, where the next ingestion Job
# (Job indexer or CronJob reindex) reads it as one batch (Assignment 03 Part A, demo step).
#
#   scripts/upload_batch.sh <folder> [batch-name]
#   scripts/upload_batch.sh --remove <batch-name>   # delete an uploaded batch folder again
#
# Use it for batches too large for the ingest-batch ConfigMap (about 750 KB of PDF after
# base64; real FAST PDFs are 1-15 MB). Files land in /pipeline-data/incoming/<batch-name>/.
# Put an _index.json in the folder to give PDFs their title and version, for example
#   [{"file": "notice.pdf", "title": "Exam notice", "doc_version": "2026-11"}]
# Without it, a PDF has no title or version and verification quarantines it (completeness).
#
# A short-lived pod mounts the PVC, kubectl cp copies the files, and the pod is deleted.
# The pod only copies files: it never touches Chroma, so the indexer stays the only writer.
set -euo pipefail

USAGE="usage: scripts/upload_batch.sh <folder> [batch-name] | --remove <batch-name>"
REMOVE=""
if [ "${1:-}" = "--remove" ]; then
  REMOVE=1; NAME=${2:?$USAGE}
else
  DIR=${1:?$USAGE}
  [ -d "$DIR" ] || { echo "not a folder: $DIR" >&2; exit 2; }
  NAME=${2:-$(basename "$(cd "$DIR" && pwd)")}
fi
NS=${NAMESPACE:-rahbar}
POD=batch-upload

[[ "$NAME" =~ ^[a-z0-9][a-z0-9._-]*$ ]] || {
  echo "batch name must be lowercase letters, digits, '.', '_' or '-': $NAME" >&2; exit 2; }
if [ "$(kubectl -n "$NS" get job indexer -o jsonpath='{.status.active}' 2>/dev/null)" = "1" ]; then
  echo "Job indexer is running; upload after it finishes (both use the lake)" >&2; exit 1
fi

kubectl -n "$NS" delete pod "$POD" --ignore-not-found --wait >/dev/null
kubectl -n "$NS" run "$POD" --image=rahbar-indexer:dev --image-pull-policy=IfNotPresent \
  --restart=Never --labels=app.kubernetes.io/part-of=rahbar --overrides='{
  "spec": {
    "automountServiceAccountToken": false,
    "enableServiceLinks": false,
    "securityContext": {"runAsNonRoot": true, "runAsUser": 10001, "runAsGroup": 10001,
                        "fsGroup": 10001, "seccompProfile": {"type": "RuntimeDefault"}},
    "containers": [{
      "name": "batch-upload", "image": "rahbar-indexer:dev", "imagePullPolicy": "IfNotPresent",
      "command": ["sleep", "600"],
      "securityContext": {"allowPrivilegeEscalation": false, "capabilities": {"drop": ["ALL"]}},
      "resources": {"requests": {"cpu": "10m", "memory": "32Mi"},
                    "limits": {"cpu": "200m", "memory": "128Mi"}},
      "volumeMounts": [{"name": "pipeline-data", "mountPath": "/pipeline-data"}]}],
    "volumes": [{"name": "pipeline-data", "persistentVolumeClaim": {"claimName": "pipeline-data"}}]
  }}' >/dev/null
trap 'kubectl -n "$NS" delete pod "$POD" --wait=false >/dev/null 2>&1 || true' EXIT
kubectl -n "$NS" wait --for=condition=Ready "pod/$POD" --timeout=120s >/dev/null

if [ -n "$REMOVE" ]; then
  # Documents already ingested stay in the lake; this only stops later runs re-reading them.
  kubectl -n "$NS" exec "$POD" -- rm -rf "/pipeline-data/incoming/$NAME"
  echo "removed /pipeline-data/incoming/$NAME"
  exit 0
fi
kubectl -n "$NS" exec "$POD" -- mkdir -p "/pipeline-data/incoming/$NAME"
kubectl -n "$NS" cp "$DIR/." "$POD:/pipeline-data/incoming/$NAME"
echo "uploaded to /pipeline-data/incoming/$NAME:"
kubectl -n "$NS" exec "$POD" -- ls -l "/pipeline-data/incoming/$NAME"
echo "next: kubectl -n $NS delete job indexer --ignore-not-found && kubectl apply -k k8s/overlays/dev"
