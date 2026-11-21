#!/usr/bin/env python3
"""Measure the pinned FastEmbed model on semantic and timing pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def vector_values(vector: object) -> list[float]:
    values = vector.tolist() if hasattr(vector, "tolist") else list(vector)  # type: ignore[arg-type]
    return [float(value) for value in values]


def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if not left_norm or not right_norm:
        raise ValueError("embedding returned a zero vector")
    return dot / (left_norm * right_norm)


def sha256_files(root: Path) -> list[dict[str, str]]:
    files = []
    for path in sorted(root.rglob("*.onnx")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({"file": path.name, "sha256": digest})
    return files


def percentile(values: list[float], fraction: float) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[round(fraction * 100) - 1]


def run(args: argparse.Namespace) -> dict:
    data = json.loads(args.pairs.read_text(encoding="utf-8"))
    seed = int(args.seed if args.seed is not None else data.get("seed", 20261121))
    random.seed(seed)
    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    os.environ["OPENBLAS_NUM_THREADS"] = str(args.threads)
    os.environ["MKL_NUM_THREADS"] = str(args.threads)

    import numpy as np
    from fastembed import TextEmbedding
    import importlib.metadata as metadata

    np.random.seed(seed)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    encoder = TextEmbedding(model_name=args.model, cache_dir=str(args.cache_dir),
                            threads=args.threads, providers=["CPUExecutionProvider"])
    positive = data["paraphrase_pairs"]
    negative = data["unrelated_pairs"]
    all_pairs = positive + negative
    unique_texts = list(dict.fromkeys(text for pair in all_pairs for text in (pair["a"], pair["b"])))
    encoded = [vector_values(vector) for vector in encoder.embed(unique_texts, batch_size=32)]
    by_text = dict(zip(unique_texts, encoded, strict=True))

    def pair_scores(pairs: list[dict]) -> list[dict]:
        return [{"id": pair["id"], "cosine": round(cosine(by_text[pair["a"]], by_text[pair["b"]]), 8)}
                for pair in pairs]

    positive_scores = pair_scores(positive)
    negative_scores = pair_scores(negative)
    positive_mean = statistics.fmean(row["cosine"] for row in positive_scores)
    negative_mean = statistics.fmean(row["cosine"] for row in negative_scores)

    timing_texts = [pair["a"] for pair in positive]
    random.Random(seed).shuffle(timing_texts)
    next(encoder.embed([timing_texts[0]], batch_size=1))  # warm model; excludes initialization
    per_chunk_seconds = []
    for text in timing_texts:
        started = time.perf_counter()
        next(encoder.embed([text], batch_size=1))
        per_chunk_seconds.append(time.perf_counter() - started)

    deterministic_text = positive[0]["a"]
    repeated = [vector_values(next(encoder.embed([deterministic_text], batch_size=1)))
                for _ in range(2)]
    absolute_differences = [abs(a - b) for a, b in zip(*repeated, strict=True)]
    if not encoded or not encoded[0]:
        raise ValueError("model returned no embedding dimensions")

    try:
        runtime_version = metadata.version("onnxruntime")
    except metadata.PackageNotFoundError:
        runtime_version = "unknown"
    try:
        fastembed_version = metadata.version("fastembed")
    except metadata.PackageNotFoundError:
        fastembed_version = "unknown"

    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "model": {"name": args.model, "fastembed_version": fastembed_version,
                  "onnxruntime_version": runtime_version, "dimensions": len(encoded[0]),
                  "device": "CPUExecutionProvider", "onnx_files": sha256_files(args.cache_dir)},
        "hardware": {"platform": platform.platform(), "processor": platform.processor(),
                     "logical_cpu_count": os.cpu_count(), "python": sys.version.split()[0],
                     "threads_per_session": args.threads},
        "semantic_similarity": {
            "paraphrase_count": len(positive_scores), "paraphrase_mean_cosine": round(positive_mean, 8),
            "unrelated_count": len(negative_scores), "unrelated_mean_cosine": round(negative_mean, 8),
            "mean_gap_paraphrase_minus_unrelated": round(positive_mean - negative_mean, 8),
            "paraphrase_pairs": positive_scores, "unrelated_pairs": negative_scores,
        },
        "per_chunk_embedding_time": {
            "measurement": "warm model; one passage per call; batch_size=1; initialization excluded",
            "sample_count": len(per_chunk_seconds),
            "mean_seconds": round(statistics.fmean(per_chunk_seconds), 8),
            "median_seconds": round(statistics.median(per_chunk_seconds), 8),
            "p95_seconds": round(percentile(per_chunk_seconds, 0.95), 8),
            "samples_seconds": [round(value, 8) for value in per_chunk_seconds],
        },
        "same_text_determinism": {
            "repeats": 2, "max_absolute_component_difference": round(max(absolute_differences), 12),
            "mean_absolute_component_difference": round(statistics.fmean(absolute_differences), 12),
            "cosine_similarity": round(cosine(*repeated), 12),
        },
    }


def markdown(result: dict) -> str:
    similarity = result["semantic_similarity"]
    timing = result["per_chunk_embedding_time"]
    determinism = result["same_text_determinism"]
    hardware = result["hardware"]
    model = result["model"]
    return f"""# D1B5 embedding module evaluation

Run timestamp (UTC): `{result['created_at']}`
Seed: `{result['seed']}`
Model: `{model['name']}` ({model['dimensions']} dimensions), FastEmbed `{model['fastembed_version']}`, ONNX Runtime `{model['onnxruntime_version']}`
Device: `{model['device']}`; ONNX file SHA-256: `{', '.join(f"{item['file']}={item['sha256']}" for item in model['onnx_files']) or 'not found in cache'}`
Hardware: `{hardware['processor']}`, {hardware['logical_cpu_count']} logical CPUs, `{hardware['platform']}`, Python `{hardware['python']}`, {hardware['threads_per_session']} thread(s).

## Semantic module results

| Pair type | Count | Mean cosine |
| --- | ---: | ---: |
| Paraphrase | {similarity['paraphrase_count']} | {similarity['paraphrase_mean_cosine']:.6f} |
| Unrelated | {similarity['unrelated_count']} | {similarity['unrelated_mean_cosine']:.6f} |
| Gap (paraphrase - unrelated) | n/a | {similarity['mean_gap_paraphrase_minus_unrelated']:.6f} |

## Timing and repeatability

Per-chunk embedding used a warm encoder, one text per call (`batch_size=1`); model initialization is excluded. Across {timing['sample_count']} samples: mean `{timing['mean_seconds']:.6f}s`, median `{timing['median_seconds']:.6f}s`, p95 `{timing['p95_seconds']:.6f}s`.

Encoding identical text twice produced cosine `{determinism['cosine_similarity']:.12f}`, maximum component difference `{determinism['max_absolute_component_difference']:.12g}`, and mean absolute component difference `{determinism['mean_absolute_component_difference']:.12g}`.

The raw pair scores, timing samples, seed, machine details, and model file digest are in `module-eval.json`. Results are CPU- and machine-specific; use the same pinned model, runtime, thread count, and seed when comparing reruns.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=Path, default=HERE / "module_pairs.json")
    parser.add_argument("--out", type=Path, default=HERE / "results" / "module-eval.json")
    parser.add_argument("--report", type=Path, default=HERE / "results" / "module-eval.md")
    parser.add_argument("--cache-dir", type=Path,
                        default=Path.home() / ".cache" / "fastembed")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be at least 1")
    result = run(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    args.report.write_text(markdown(result), encoding="utf-8")
    print(markdown(result))
    print(f"\nWrote {args.out} and {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
