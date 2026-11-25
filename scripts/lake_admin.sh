#!/usr/bin/env bash
# Run one data-lake maintenance command as a Kubernetes Job with the indexer image (the only
# Chroma writer), then print the per-document chunk counts (Assignment 03 A2).
#   scripts/lake_admin.sh --delete library-policy.md
#   scripts/lake_admin.sh --restore-version faculty-entrepreneurship-and-technical-start-ups-policy.pdf
#   scripts/lake_admin.sh --counts-only
# COUNT_SOURCE=<file> also prints the explicit `where source == <file>` count.
set -euo pipefail
ARGS="$*"
COUNT_ARGS=${COUNT_SOURCE:+--source $COUNT_SOURCE}
RUN="python -m pipeline.run $ARGS"
[ "$ARGS" = "--counts-only" ] && RUN="true"
kubectl -n rahbar delete job lake-admin --ignore-not-found >/dev/null
kubectl apply -f - <<YAML
apiVersion: batch/v1
kind: Job
metadata: {name: lake-admin, namespace: rahbar, labels: {app.kubernetes.io/name: indexer, app.kubernetes.io/part-of: rahbar}}
spec:
  backoffLimit: 0
  template:
    metadata: {labels: {app.kubernetes.io/name: indexer, app.kubernetes.io/part-of: rahbar}}
    spec:
      restartPolicy: Never
      serviceAccountName: rahbar-indexer
      automountServiceAccountToken: false
      enableServiceLinks: false
      securityContext: {runAsNonRoot: true, runAsUser: 10001, runAsGroup: 10001, fsGroup: 10001, seccompProfile: {type: RuntimeDefault}}
      containers:
        - name: indexer
          image: rahbar-indexer:dev
          imagePullPolicy: IfNotPresent
          command: ["/bin/sh", "-c", "$RUN && python -m pipeline.counts $COUNT_ARGS"]
          envFrom: [{configMapRef: {name: rahbar-config}}]
          env: [{name: BATCH_DIR, value: /batch}]
          resources: {requests: {cpu: 500m, memory: 1Gi}, limits: {cpu: "2", memory: 3Gi}}
          securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: ["ALL"]}}
          volumeMounts:
            - {name: corpus, mountPath: /corpus, readOnly: true}
            - {name: pipeline-data, mountPath: /pipeline-data}
            - {name: batch, mountPath: /batch, readOnly: true}
            - {name: tmp, mountPath: /tmp}
      volumes:
        - {name: corpus, persistentVolumeClaim: {claimName: corpus}}
        - {name: pipeline-data, persistentVolumeClaim: {claimName: pipeline-data}}
        - {name: batch, configMap: {name: ingest-batch, optional: true}}
        - {name: tmp, emptyDir: {sizeLimit: 1Gi}}
YAML
kubectl -n rahbar wait --for=condition=complete --timeout=30m job/lake-admin >/dev/null || true
kubectl -n rahbar get job lake-admin
kubectl -n rahbar logs job/lake-admin | python3 -c '
import json, sys
for line in sys.stdin:
    if not line.startswith("{"):
        if "onnxruntime" not in line and not line.startswith("{\"collection"): print(line.rstrip())
        continue
    d = json.loads(line)
    if d.get("msg") == "lake": print("  lake:", d["action"])
    elif d.get("msg") == "verification report written":
        print("  run:", {k: d[k] for k in ("unchanged", "verified", "lake_current", "lake_superseded", "lake_deleted", "embedded_chunks", "reused_chunks")})
    elif d.get("msg") == "index unchanged: every document reused, active collection kept":
        print("  index unchanged, collection kept:", d["collection"])
    elif d.get("msg") == "indexer finished": print("  new collection:", d["collection"])
'
