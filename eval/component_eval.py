#!/usr/bin/env python3
"""Score retrieved document/page rankings and a controlled three-noise stress case."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def relevant(item: dict, gold: list[dict]) -> bool:
    return any(item.get("source", "").casefold() == g.get("source", "").casefold()
               and (g.get("page") is None or item.get("page") == g.get("page"))
               and (not g.get("section") or str(item.get("section", "")).startswith(str(g["section"])))
               for g in gold)


def score(rows: list[dict], *, noise: bool = False) -> dict:
    recall3, recall5, mrr, ndcg5 = [], [], [], []
    for row in rows:
        gold = row.get("relevant") or []
        if not gold:
            continue
        ranked = row.get("retrieved") or []
        if noise:
            ranked = [{"source": f"__irrelevant_noise_{i}__", "page": None} for i in range(3)] + ranked
        hits = [relevant(item, gold) for item in ranked]
        matched = {gidx for gidx, g in enumerate(gold)
                   if any(relevant(item, [g]) for item in ranked[:5])}
        recall3.append(len({gidx for gidx, g in enumerate(gold)
                           if any(relevant(item, [g]) for item in ranked[:3])}) / len(gold))
        recall5.append(len(matched) / len(gold))
        rank = next((i + 1 for i, hit in enumerate(hits[:5]) if hit), None)
        mrr.append(1 / rank if rank else 0.0)
        dcg = sum((1 / math.log2(i + 2)) for i, hit in enumerate(hits[:5]) if hit)
        ideal_hits = min(len(gold), 5)
        idcg = sum(1 / math.log2(i + 2) for i in range(ideal_hits))
        ndcg5.append(dcg / idcg if idcg else 0.0)
    def mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None
    return {"n_answerable": len(recall5), "recall@3": mean(recall3), "recall@5": mean(recall5),
            "mrr": mean(mrr), "ndcg@5": mean(ndcg5)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="run_eval.py JSON result")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    rows = data.get("rows", [])
    if not rows or not any(row.get("retrieved") for row in rows):
        parser.error("input must contain per-question retrieved document/page rankings")
    base = score(rows)
    stress = score(rows, noise=True)
    result = {"input": str(args.input), "baseline": base,
              "controlled_noise": {"condition": "prepend three synthetic irrelevant candidates to each ranking",
                                   "metrics": stress,
                                   "delta": {key: round(stress[key] - base[key], 6)
                                             for key in ("recall@3", "recall@5", "mrr", "ndcg@5")
                                             if stress[key] is not None and base[key] is not None}}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
