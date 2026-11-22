#!/usr/bin/env python3
"""Compare an evaluation result with its baseline using release ConfigMap thresholds."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import yaml


DEFAULTS = {
    "MAX_RECALL5_DROP": 0.05,
    "MIN_FAITHFULNESS": 0.90,
    "MAX_P95_SECONDS": 15.0,
}


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def thresholds(path: Path) -> dict[str, float]:
    if path.is_dir():
        data = {key: (path / key).read_text(encoding="utf-8").strip()
                for key in DEFAULTS if (path / key).is_file()}
    else:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        data = raw.get("data", raw)
    values = {key: float(data.get(key, default)) for key, default in DEFAULTS.items()}
    for key, value in values.items():
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{key} must be a finite, non-negative number")
    if values["MIN_FAITHFULNESS"] > 1 or values["MAX_RECALL5_DROP"] > 1:
        raise ValueError("fraction thresholds must be between 0 and 1")
    return values


def evaluate(candidate: dict, baseline: dict, faithfulness: dict,
             limits: dict[str, float]) -> list[str]:
    failures = []
    pairs = (
        ("recall@5", candidate.get("recall@5"), baseline.get("recall@5")),
        ("abstention_correctness", candidate.get("abstention_correctness"),
         baseline.get("abstention_correctness")),
    )
    for name, actual, previous in pairs:
        if actual is None or previous is None:
            failures.append(f"{name}: missing candidate or baseline value")
        elif not math.isfinite(float(actual)) or not math.isfinite(float(previous)):
            failures.append(f"{name}: values must be finite")
        elif name == "recall@5" and float(actual) < float(previous) - limits["MAX_RECALL5_DROP"] - 1e-9:
            failures.append(f"recall@5 {float(actual):.3f} is below allowed baseline floor "
                            f"{float(previous) - limits['MAX_RECALL5_DROP']:.3f}")
        elif name == "abstention_correctness" and float(actual) < float(previous) - 1e-9:
            failures.append(f"abstention correctness {float(actual):.3f} is worse than baseline "
                            f"{float(previous):.3f}")

    faith = faithfulness.get("score")
    if faith is None or not math.isfinite(float(faith)):
        failures.append("faithfulness: missing or non-finite manual-review score")
    elif float(faith) < limits["MIN_FAITHFULNESS"]:
        failures.append(f"faithfulness {float(faith):.3f} is below minimum "
                        f"{limits['MIN_FAITHFULNESS']:.3f}")

    p95 = candidate.get("latency_p95_seconds")
    if p95 is None or not math.isfinite(float(p95)):
        failures.append("p95 latency: missing or non-finite candidate value")
    elif float(p95) > limits["MAX_P95_SECONDS"]:
        failures.append(f"p95 latency {float(p95):.3f}s exceeds maximum "
                        f"{limits['MAX_P95_SECONDS']:.3f}s")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True, help="run_eval JSON result")
    parser.add_argument("--baseline", type=Path, required=True, help="frozen baseline JSON")
    parser.add_argument("--faithfulness", type=Path, required=True,
                        help="human-reviewed faithfulness result JSON")
    parser.add_argument("--configmap", type=Path, required=True,
                        help="Kubernetes ConfigMap YAML or extracted data YAML")
    args = parser.parse_args()
    try:
        failures = evaluate(read_json(args.candidate), read_json(args.baseline),
                            read_json(args.faithfulness), thresholds(args.configmap))
    except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    if failures:
        print("REJECT")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS: candidate meets recall@5, faithfulness, p95 latency, and abstention gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
