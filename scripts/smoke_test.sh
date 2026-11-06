#!/usr/bin/env bash
# Smoke test through the Ingress (section 6, cd.yml deploy; also run by ci.yml e2e-eval).
#
# Usage: scripts/smoke_test.sh <base-url> <host-header>
#   e.g. scripts/smoke_test.sh http://localhost rahbar.local
#
# Passes when: the ui answers / with 200, and POST /api/ask answers 200 with a request_id and
# a non-empty retrieved list. Retries for up to a minute, because the Ingress controller picks
# up new endpoints a few seconds after a rollout finishes.
set -euo pipefail

base="${1:?usage: smoke_test.sh <base-url> <host-header>}"
host="${2:?host-header}"
question='{"question": "What is the minimum attendance?"}'
body="$(mktemp)"

for attempt in $(seq 1 12); do
  ui_status="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${host}" "${base}/" || true)"
  ask_status="$(curl -s -o "$body" -w '%{http_code}' -H "Host: ${host}" \
    -H 'Content-Type: application/json' -d "$question" "${base}/api/ask" || true)"
  if [[ "$ui_status" == "200" && "$ask_status" == "200" ]]; then
    break
  fi
  echo "attempt ${attempt}: ui=${ui_status} ask=${ask_status}; retrying in 5 s"
  sleep 5
done

echo "GET / -> ${ui_status}; POST /api/ask -> ${ask_status}"
[[ "$ui_status" == "200" && "$ask_status" == "200" ]] || { cat "$body" >&2; exit 1; }

python3 - "$body" <<'EOF'
import json
import sys

response = json.load(open(sys.argv[1]))
retrieved = response.get("retrieved") or []
print(json.dumps({
    "request_id": response.get("request_id"),
    "provider": response.get("provider"),
    "answered_from_context": response.get("answered_from_context"),
    "retrieved": [(r.get("source"), r.get("section"), round(r.get("score", 0), 3))
                  for r in retrieved],
}, indent=2))
if not response.get("request_id"):
    sys.exit("FAIL: no request_id in the response")
if not retrieved:
    sys.exit("FAIL: retrieved is empty, so the index is missing or the api cannot reach Chroma")
print("smoke test passed")
EOF
