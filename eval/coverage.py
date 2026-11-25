#!/usr/bin/env python3
"""Assignment 03 E2/E4: query coverage of the golden set (RAGOps paper 4.2.7).

    python eval/coverage.py --out eval/results/coverage-before.json      # exit 1 below MIN_SHARE

For every live query, find the most similar golden question (cosine of the pinned embedding
model). A query is covered when that similarity reaches the threshold. The coverage share is
covered / all live queries; the script exits 1 when the share is below --min-share (default
0.85, the paper's example: "if less than 85% of live queries achieve a certain similarity
score to test queries, the system should prompt a test set expansion").

Threshold (default `auto`): the midpoint between the highest unrelated-pair cosine and the
lowest paraphrase-pair cosine in eval/module_pairs.json, i.e. the score that separates "the
same question in other words" from "a different question" for this model.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norms = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norms if norms else 0.0


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--queries", type=Path, default=HERE / "coverage_queries.jsonl")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.jsonl")
    parser.add_argument("--pairs", type=Path, default=HERE / "module_pairs.json")
    parser.add_argument("--threshold", default="auto",
                        help="cosine threshold for a covered query, or 'auto' (see above)")
    parser.add_argument("--min-share", type=float, default=0.85)
    parser.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--cache-dir", type=Path,
                        default=Path(os.environ.get("EMBED_CACHE_DIR",
                                                    Path.home() / ".cache" / "fastembed")))
    parser.add_argument("--out", type=Path, default=HERE / "results" / "coverage.json")
    args = parser.parse_args()
    queries, golden = read_jsonl(args.queries), read_jsonl(args.golden)
    if len(queries) < 40:
        parser.error("E1 needs at least 40 live queries")

    from fastembed import TextEmbedding
    model = TextEmbedding(model_name=args.model, cache_dir=str(args.cache_dir), threads=1)

    def vectors(texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in model.embed(texts, batch_size=32)]

    pairs = json.loads(args.pairs.read_text(encoding="utf-8"))

    def pair_scores(items: list[dict]) -> list[float]:
        left, right = vectors([p["a"] for p in items]), vectors([p["b"] for p in items])
        return [cosine(a, b) for a, b in zip(left, right, strict=True)]

    paraphrase, unrelated = pair_scores(pairs["paraphrase_pairs"]), \
        pair_scores(pairs["unrelated_pairs"])
    if args.threshold == "auto":
        threshold = round((max(unrelated) + min(paraphrase)) / 2, 4)
        rule = (f"auto: midpoint of max unrelated-pair cosine {max(unrelated):.3f} and min "
                f"paraphrase-pair cosine {min(paraphrase):.3f} ({len(unrelated)} + "
                f"{len(paraphrase)} pairs in {args.pairs.name})")
    else:
        threshold, rule = float(args.threshold), "fixed by --threshold"

    golden_vectors = vectors([g["question"] for g in golden])
    rows = []
    for query, vector in zip(queries, vectors([q["question"] for q in queries]), strict=True):
        sims = [cosine(vector, g) for g in golden_vectors]
        best = max(range(len(sims)), key=sims.__getitem__)
        rows.append({"id": query["id"], "scope": query["scope"], "topic": query["topic"],
                     "question": query["question"], "closest_golden_id": golden[best]["id"],
                     "closest_golden_question": golden[best]["question"],
                     "max_cosine": round(sims[best], 4),
                     "covered": sims[best] >= threshold})
    covered = sum(r["covered"] for r in rows)
    share = covered / len(rows)
    uncovered: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if not row["covered"]:
            uncovered[row["topic"]].append(f"{row['id']} ({row['max_cosine']:.3f}) "
                                           f"{row['question']}")
    by_scope = {scope: {"n": len(group), "covered": sum(r["covered"] for r in group),
                        "mean_max_cosine": round(statistics.fmean(r["max_cosine"]
                                                                  for r in group), 4)}
                for scope in ("in_scope", "out_of_scope")
                if (group := [r for r in rows if r["scope"] == scope])}
    result = {
        "created_at": datetime.now(timezone.utc).isoformat(), "model": args.model,
        "golden": str(args.golden), "golden_questions": len(golden),
        "live_queries": len(rows), "threshold": threshold, "threshold_rule": rule,
        "covered": covered, "coverage_share": round(share, 4), "min_share": args.min_share,
        "decision": "PASS" if share >= args.min_share else "FAIL: expand the golden set",
        "by_scope": by_scope, "uncovered_by_topic": dict(sorted(uncovered.items())),
        "queries": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"golden questions: {len(golden)}   live queries: {len(rows)}")
    print(f"threshold: {threshold}  ({rule})")
    print(f"coverage: {covered}/{len(rows)} = {share:.1%}  (minimum {args.min_share:.0%})")
    for scope, values in by_scope.items():
        print(f"  {scope}: {values['covered']}/{values['n']} covered, mean best cosine "
              f"{values['mean_max_cosine']}")
    print("uncovered queries by topic:")
    for topic, items in sorted(uncovered.items()):
        print(f"  {topic} ({len(items)})")
        for item in items:
            print(f"    - {item}")
    print(f"decision: {result['decision']}   (written to {args.out})")
    return 0 if share >= args.min_share else 1


if __name__ == "__main__":
    raise SystemExit(main())
