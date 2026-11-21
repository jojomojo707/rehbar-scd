#!/usr/bin/env python3
"""Measure golden-question coverage with pinned FastEmbed; fail below threshold."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** .5
    nb = sum(y * y for y in b) ** .5
    return dot / (na * nb) if na and nb else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, default=HERE / "coverage_queries.jsonl")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.jsonl")
    parser.add_argument("--threshold", type=float, default=0.65,
                        help="fixed cosine coverage threshold (default: 0.65)")
    parser.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache" / "fastembed")
    parser.add_argument("--out", type=Path, default=HERE / "results" / "coverage.json")
    args = parser.parse_args()
    queries = [json.loads(line) for line in args.queries.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    golden = [json.loads(line) for line in args.golden.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not queries or not golden:
        parser.error("queries and golden set must be non-empty JSONL")
    if sum(q["scope"] == "in_scope" for q in queries) < 28 or sum(q["scope"] == "out_of_scope" for q in queries) < 12:
        parser.error("need at least 28 in-scope and 12 out-of-scope queries")
    from fastembed import TextEmbedding
    embedder = TextEmbedding(model_name=args.model, cache_dir=str(args.cache_dir), threads=1,
                             providers=["CPUExecutionProvider"])
    texts = [q["question"] for q in queries] + [g["question"] for g in golden]
    vectors = [v.tolist() for v in embedder.embed(texts, batch_size=32)]
    q_vectors = vectors[:len(queries)]
    g_vectors = vectors[len(queries):]
    rows = []
    for query, vector in zip(queries, q_vectors, strict=True):
        sims = [cosine(vector, g) for g in g_vectors]
        best = max(range(len(sims)), key=sims.__getitem__)
        rows.append({"id": query["id"], "scope": query["scope"], "topic": query["topic"],
                     "question": query["question"], "closest_golden_id": golden[best]["id"],
                     "max_cosine": round(sims[best], 8)})
    positives = [r["max_cosine"] for r in rows if r["scope"] == "in_scope"]
    negatives = [r["max_cosine"] for r in rows if r["scope"] == "out_of_scope"]
    positive_floor, negative_ceiling = min(positives), max(negatives)
    threshold = args.threshold
    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row["scope"] == "in_scope" and row["max_cosine"] < threshold:
            groups[row["topic"]].append(row["id"])
    result = {"created_at": datetime.now(timezone.utc).isoformat(), "model": args.model,
              "threshold": threshold, "threshold_rule": f"fixed cosine threshold {threshold}",
              "in_scope": {"n": len(positives), "mean": statistics.fmean(positives), "min": positive_floor},
              "out_of_scope": {"n": len(negatives), "mean": statistics.fmean(negatives),
                               "max": negative_ceiling,
                               "above_threshold": sum(score >= threshold for score in negatives),
                               "false_positive_rate": sum(score >= threshold for score in negatives) / len(negatives)},
              "threshold_justification": ("On the labeled baseline sample, 0.65 surfaced uncovered in-scope queries; held fixed for comparison. Out-of-scope scores overlap, so this prompts coverage review rather than guaranteeing answerability."
                                          if threshold == 0.65 else "User-specified threshold used to demonstrate a nonzero coverage-gate failure."),
              "uncovered_topics": dict(groups), "queries": rows,
              "limitation": "Threshold evidence is synthetic and only 40 queries; use human-reviewed live queries before production use."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "queries"}, indent=2))
    print(f"Wrote {args.out}")
    return 1 if any(row["scope"] == "in_scope" and row["max_cosine"] < threshold for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
