#!/usr/bin/env python3
"""Assignment 03 D2/D3: inspect the API's JSONL query traces.

    python eval/trace.py trace <trace-id> --trace-dir traces/      # context + exact prompt
    python eval/trace.py summary --since 2026-11-26T08:00:00Z --until 2026-11-26T12:00:00Z

`trace` prints the stored record, then the exact context passages and the reconstructed prompt
messages that produced the answer. `summary` reports, over a time window: the top-1 retrieval
similarity distribution, abstention rate, cache hit rate, p95 latency per stage and the number
of injection attempts flagged (query rail and context rail).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path


def read_traces(root: Path) -> list[dict]:
    by_id = {}
    for path in sorted(root.glob("**/*.jsonl")):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "trace_id" not in row and isinstance(row.get("trace"), dict):
                row = row["trace"]          # a `kubectl logs` line wraps the trace
            if row.get("trace_id"):
                by_id[row["trace_id"]] = row
    return list(by_id.values())


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, round((len(ordered) - 1) * p))], 4)


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def show(row: dict) -> None:
    print(json.dumps({k: v for k, v in row.items() if k not in ("prompt",)}, indent=2,
                     ensure_ascii=False))
    print("\n=== context: the passages the model saw, in rank order ===")
    for rank, passage in enumerate(row.get("retrieved") or [], 1):
        print(f"[{rank}] {passage.get('chunk_id')}  {passage.get('document')} v"
              f"{passage.get('version')}  page {passage.get('page')}  score "
              f"{passage.get('score')}  superseded={passage.get('superseded')}")
    prompt = row.get("prompt") or []
    print("\n=== reconstructed prompt ===")
    if not prompt:
        print("No prompt: the answer came from the cache or abstained before generation.")
    for message in prompt:
        print(f"[{message['role']}]\n{message['content']}\n")
    if prompt:
        digest = hashlib.sha256(json.dumps(prompt, ensure_ascii=False,
                                           sort_keys=True).encode()).hexdigest()
        match = "MATCHES" if digest == row.get("prompt_sha256") else "DOES NOT MATCH"
        print(f"prompt sha256 {digest} {match} the stored prompt_sha256")


def summary(rows: list[dict], since: str, until: str | None) -> dict:
    start = _time(since)
    end = _time(until) if until else None
    rows = [r for r in rows if _time(r["timestamp"]) >= start
            and (end is None or _time(r["timestamp"]) <= end)]
    top1 = [float(r["retrieved"][0]["score"]) for r in rows
            if r.get("retrieved") and r["retrieved"][0].get("score") is not None
            and r.get("cache_status") != "HIT"]
    bins = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
    histogram = {f"{lo:.1f}-{min(hi, 1.0):.1f}": sum(lo <= s < hi for s in top1)
                 for lo, hi in zip(bins, bins[1:])}
    abstained = sum(not (r.get("response") or {}).get("answered_from_context", False)
                    for r in rows)
    looked_up = [r for r in rows if r.get("cache_status") in ("HIT", "MISS")]
    hits = sum(r.get("cache_status") == "HIT" for r in rows)
    stages = ("embedding", "retrieval", "generation", "total")
    flagged_query = sum(any(a.startswith("instruction_override") for a in
                            r.get("guardrail_actions", [])) for r in rows)
    flagged_context = sum(len(r.get("injection_flags") or []) for r in rows)
    return {
        "window": {"since": since, "until": until, "requests": len(rows)},
        "top1_similarity": {"n": len(top1), "min": min(top1) if top1 else None,
                            "p10": percentile(top1, .10), "p50": percentile(top1, .50),
                            "p90": percentile(top1, .90), "max": max(top1) if top1 else None,
                            "histogram": histogram},
        "abstention_rate": round(abstained / len(rows), 4) if rows else None,
        "cache": {"hits": hits, "lookups": len(looked_up),
                  "hit_rate": round(hits / len(looked_up), 4) if looked_up else None,
                  "bypassed": sum(r.get("cache_status") == "BYPASS" for r in rows)},
        "stage_p95_ms": {s: percentile([float(r["stage_ms"][s]) for r in rows
                                        if s in (r.get("stage_ms") or {})], .95) for s in stages},
        "injection_attempts_flagged": {"query_rail": flagged_query,
                                       "context_rail": flagged_context,
                                       "total": flagged_query + flagged_context},
        "collections_seen": sorted({str(r.get("collection_version")) for r in rows}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("trace", help="print the context and prompt behind one answer")
    one.add_argument("trace_id")
    one.add_argument("--trace-dir", type=Path, default=Path("traces"))
    many = sub.add_parser("summary", help="metrics over a time window")
    many.add_argument("--since", default="1970-01-01T00:00:00+00:00")
    many.add_argument("--until")
    many.add_argument("--trace-dir", type=Path, default=Path("traces"))
    args = parser.parse_args()
    rows = read_traces(args.trace_dir)
    if args.command == "trace":
        row = next((item for item in rows if item.get("trace_id") == args.trace_id), None)
        if row is None:
            parser.error(f"trace id {args.trace_id!r} was not found in {args.trace_dir}")
        show(row)
        return 0
    print(json.dumps(summary(rows, args.since, args.until), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
