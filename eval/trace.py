#!/usr/bin/env python3
"""Inspect persisted API JSONL traces and reconstruct the saved prompt."""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path


def read_traces(root: Path) -> list[dict]:
    by_id = {}
    for path in sorted(root.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                row = json.loads(line)
                if "trace_id" not in row and isinstance(row.get("trace"), dict):
                    row = row["trace"]
                if row.get("trace_id"):
                    by_id[row["trace_id"]] = row
    return list(by_id.values())


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values.sort()
    return values[min(len(values) - 1, round((len(values) - 1) * p))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    trace = sub.add_parser("trace", help="show one request and its saved prompt")
    trace.add_argument("trace_id")
    trace.add_argument("--trace-dir", type=Path, default=Path("traces"))
    summary = sub.add_parser("summary", help="summarize traces since an ISO timestamp")
    summary.add_argument("--since", default="1970-01-01T00:00:00+00:00")
    summary.add_argument("--trace-dir", type=Path, default=Path("traces"))
    args = parser.parse_args()
    rows = read_traces(args.trace_dir)
    if args.command == "trace":
        row = next((item for item in rows if item.get("trace_id") == args.trace_id), None)
        if row is None:
            parser.error(f"trace id {args.trace_id!r} was not found")
        print(json.dumps(row, indent=2, ensure_ascii=False))
        print("\n--- reconstructed prompt ---")
        prompt = row.get("prompt") or []
        if not prompt:
            print("Prompt unavailable for cache hit or abstention before generation.")
        for message in prompt:
            print(f"[{message['role']}]\n{message['content']}\n")
        return 0

    since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    rows = [r for r in rows if datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")) >= since]
    top = [float(r["retrieved"][0]["score"]) for r in rows if r.get("retrieved")]
    abstained = sum(not r.get("response", {}).get("answered_from_context", False) for r in rows)
    latencies = {name: [float(r.get("stage_ms", {}).get(name, 0)) for r in rows
                        if name in r.get("stage_ms", {})]
                 for name in ("embedding", "retrieval", "generation", "total")}
    print(json.dumps({
        "requests": len(rows), "mean_top1_similarity": statistics.fmean(top) if top else None,
        "abstention_rate": abstained / len(rows) if rows else None,
        "cache_hits": sum(r.get("cache_status") == "HIT" for r in rows),
        "stage_p95_ms": {name: percentile(values, .95) for name, values in latencies.items()},
        "flagged_injections": sum("instruction_override_removed_from_retrieval_query" in r.get("guardrail_actions", []) for r in rows),
        "since": args.since,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
