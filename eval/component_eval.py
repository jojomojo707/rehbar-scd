#!/usr/bin/env python3
"""Component level (retrieval): recall@3, recall@5, MRR and nDCG@5 over the golden set.

A retrieved chunk is relevant when its document matches a gold location and, if the gold
location names a page, its page matches too. Metrics are averaged over answerable questions.

The noise test (`typo_query`) adds seeded typos to each golden query; run_suite.py sends the
perturbed queries to the live retriever and reports how each metric changes.

    python eval/component_eval.py --input eval/results/<run>/e2e-run-1.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from pathlib import Path


def relevant(item: dict, gold: list[dict]) -> bool:
    return any(str(item.get("source", "")).casefold() == str(g.get("source", "")).casefold()
               and (g.get("page") is None or item.get("page") == g.get("page"))
               for g in gold)


def score(rows: list[dict]) -> dict:
    """rows: [{"relevant": [{source, page}], "retrieved": [{source, page}, ...]}, ...]"""
    recall3, recall5, mrr, ndcg5 = [], [], [], []
    for row in rows:
        gold = row.get("relevant") or []
        if not gold:
            continue
        ranked = row.get("retrieved") or []

        def found(k: int) -> float:
            return len({i for i, g in enumerate(gold)
                        if any(relevant(item, [g]) for item in ranked[:k])}) / len(gold)

        hits = [relevant(item, gold) for item in ranked[:5]]
        recall3.append(found(3))
        recall5.append(found(5))
        rank = next((i + 1 for i, hit in enumerate(hits) if hit), None)
        mrr.append(1 / rank if rank else 0.0)
        dcg = sum(1 / math.log2(i + 2) for i, hit in enumerate(hits) if hit)
        idcg = sum(1 / math.log2(i + 2) for i in range(min(len(gold), 5)))
        ndcg5.append(dcg / idcg if idcg else 0.0)

    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 6) if values else None

    return {"n_answerable": len(recall5), "recall@3": mean(recall3), "recall@5": mean(recall5),
            "mrr": mean(mrr), "ndcg@5": mean(ndcg5)}


_WORD = re.compile(r"[A-Za-z]{5,}")


def typo_query(question: str, rng: random.Random, rate: float = 0.25) -> str:
    """Swap two inner letters in about `rate` of the words of 5+ letters (at least one)."""
    words = list(_WORD.finditer(question))
    if not words:
        return question
    chosen = [m for m in words if rng.random() < rate] or [rng.choice(words)]
    text = question
    for match in sorted(chosen, key=lambda m: m.start(), reverse=True):
        word = match.group(0)
        i = rng.randrange(1, len(word) - 2)
        typo = word[:i] + word[i + 1] + word[i] + word[i + 2:]
        text = text[:match.start()] + typo + text[match.end():]
    return text


def delta(clean: dict, noisy: dict) -> dict:
    return {key: (round(noisy[key] - clean[key], 6)
                  if clean.get(key) is not None and noisy.get(key) is not None else None)
            for key in ("recall@3", "recall@5", "mrr", "ndcg@5")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="an e2e run JSON from run_suite")
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    print(json.dumps(score(data["rows"]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
