#!/usr/bin/env bash
# Ask the live API one question from inside the cluster, then read that request's trace back
# from the API pods' stdout (kubectl logs) and print the version fields (Assignment 03 D1/F3/F4).
#   scripts/trace_probe.sh ["question"]
set -euo pipefail
Q=${1:-"What is the minimum CGPA required for an undergraduate degree?"}
ID=$(kubectl -n rahbar exec deploy/api -- python -c "import httpx,sys; print(httpx.post('http://localhost:8000/api/ask', json={'question': sys.argv[1]}, timeout=120).json()['request_id'])" "$Q")
echo "asked: $Q"
echo "trace id: $ID"
kubectl -n rahbar logs -l app.kubernetes.io/name=api --since=5m --tail=-1 --prefix \
  | grep "\"trace_id\": \"$ID\"" | grep '"query trace"' | sed 's/^\[\([^]]*\)\] /\1\t/' \
  | python3 -c '
import json, sys
for line in sys.stdin:
    source, _, payload = line.partition("\t")
    t = json.loads(payload)["trace"]
    print("from kubectl logs:", source)
    for key in ("trace_id", "timestamp", "pod", "collection", "collection_version",
                "embedding_model", "embedding_version", "filters", "outcome",
                "guardrail_actions", "cache_status", "stage_ms"):
        print(f"  {key:19} {t.get(key)}")
    print("  model_parameters   ", t["model_parameters"])
    print("  retrieved          ", [(p["chunk_id"], round(p["score"], 3)) for p in t["retrieved"]][:3], "...")
    print("  answer             ", t["response"]["answer"][:150])
'
