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
import json, sys, textwrap
for line in sys.stdin:
    source, _, payload = line.partition("\t")
    t = json.loads(payload)["trace"]
    print("from kubectl logs:", source)
    for key in ("trace_id", "timestamp", "pod", "collection", "collection_version",
                "embedding_model", "embedding_version", "filters", "outcome",
                "guardrail_actions", "cache_status", "stage_ms"):
        print(f"  {key:19} {t.get(key)}")
    print("  model_parameters   ", t["model_parameters"])
    print("  retrieved (chunk id, document version, score):")
    for p in t["retrieved"]:
        chunk, version, score = p["chunk_id"], str(p.get("version")), p["score"]
        print(f"    {chunk:48} {version:10} {score:.3f}")
    print("  answer:")
    for line in textwrap.wrap(t["response"]["answer"], 100):
        print("    " + line)
'
