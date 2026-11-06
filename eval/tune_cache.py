"""Choose CACHE_THRESHOLD from labelled question pairs (brief section 3.3).

For each pair it embeds both questions with the pinned model, exactly as the api does for a
cache lookup (FastEmbedder.embed_query, then cosine as the dot product of unit vectors). For
each threshold it counts:

- true hits:  paraphrase pairs (same_answer: true) at or above the threshold, which the cache
              would correctly serve;
- false hits: near-miss pairs (same_answer: false) at or above the threshold, which the cache
              would serve WRONGLY.

The recommended threshold is the lowest one with zero false hits. No LLM, no cluster, no
network after the model has been downloaded once.

    python eval/tune_cache.py --pairs eval/cache_pairs.yaml --thresholds 0.88 0.92 0.95
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from app.providers.embedding.fastembed import FastEmbedder  # noqa: E402


def unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(unit(a), unit(b)))


def load_pairs(path: Path) -> list[dict]:
    pairs = yaml.safe_load(path.read_text(encoding="utf-8"))["pairs"]
    for pair in pairs:
        if not {"id", "a", "b", "same_answer"} <= pair.keys():
            raise SystemExit(f"pair {pair.get('id', '?')} needs id, a, b and same_answer")
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pairs", type=Path, default=ROOT / "eval" / "cache_pairs.yaml")
    parser.add_argument("--thresholds", type=float, nargs="+", default=[0.88, 0.92, 0.95])
    parser.add_argument("--model", default=os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5"))
    parser.add_argument(
        "--cache-dir",
        default=os.environ.get("EMBED_CACHE_DIR", str(Path.home() / ".cache" / "fastembed")),
        help="where fastembed keeps the model (downloaded on first use)",
    )
    args = parser.parse_args()

    pairs = load_pairs(args.pairs)
    embedder = FastEmbedder(args.model, args.cache_dir)
    for pair in pairs:
        pair["score"] = cosine(embedder.embed_query(pair["a"]), embedder.embed_query(pair["b"]))

    positives = [p for p in pairs if p["same_answer"]]
    negatives = [p for p in pairs if not p["same_answer"]]
    print(f"model {args.model}; {len(positives)} paraphrase pairs, {len(negatives)} near misses\n")

    print("All pairs, highest similarity first:")
    print(f"{'id':<5} {'label':<10} {'cosine':>7}  question a  |  question b")
    for pair in sorted(pairs, key=lambda p: -p["score"]):
        label = "paraphrase" if pair["same_answer"] else "near-miss"
        print(f"{pair['id']:<5} {label:<10} {pair['score']:7.4f}  {pair['a']}  |  {pair['b']}")

    print("\n| Threshold | True hits (paraphrases served) | False hits (wrong answer served) |")
    print("| --- | --- | --- |")
    safe: list[float] = []
    for threshold in sorted(args.thresholds):
        true_hits = [p for p in positives if p["score"] >= threshold]
        false_hits = [p for p in negatives if p["score"] >= threshold]
        if not false_hits:
            safe.append(threshold)
        names = ", ".join(f"{p['id']} ({p['score']:.4f})" for p in false_hits) or "none"
        print(f"| {threshold:.2f} | {len(true_hits)}/{len(positives)} | "
              f"{len(false_hits)}/{len(negatives)}: {names} |")

    highest_negative = max(negatives, key=lambda p: p["score"])
    print(f"\nHighest near miss: {highest_negative['id']} at {highest_negative['score']:.4f}: "
          f"\"{highest_negative['a']}\" vs \"{highest_negative['b']}\"")
    if not safe:
        print("No tested threshold has zero false hits. Try higher values.")
        return 1
    print(f"Lowest threshold with zero false hits: {safe[0]:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
