#!/usr/bin/env python3
"""Assignment 03 C2: the release gate. Compare a candidate suite result with the baseline.

    python eval/release_gate.py --candidate <dir>/suite.json --baseline <dir>/suite.json \
        --thresholds k8s/base/release-gate-configmap.yaml       # or a mounted ConfigMap dir

Thresholds come from the ConfigMap `release-gate-thresholds` (one key per file when mounted):

  MAX_RECALL5_DROP        component recall@5 may fall at most this much below the baseline
  MIN_FAITHFULNESS        the candidate's judged faithfulness must be at least this
  MAX_P95_SECONDS         the candidate's end-to-end p95 latency must be at most this
  MIN_ABSTENTION_MARGIN   abstention correctness may be at most this much below the baseline
                          (0 = "not lower than the baseline")

Each metric is the mean over the suite's repeated runs. Prints PASS or REJECT with one line per
failed threshold. Exit 0 = PASS, 1 = REJECT, 2 = invalid input.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import yaml

DEFAULTS = {
    "MAX_RECALL5_DROP": 0.02,
    "MIN_FAITHFULNESS": 0.85,
    "MAX_P95_SECONDS": 12.0,
    "MIN_ABSTENTION_MARGIN": 0.0,
}


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


def _metric(suite: dict, level: str, key: str) -> float | None:
    value = (suite.get("mean") or {}).get(level, {}).get(key)
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def evaluate(candidate: dict, baseline: dict, limits: dict[str, float]) -> list[str]:
    failures = []
    recall, base_recall = (_metric(candidate, "component", "recall@5"),
                           _metric(baseline, "component", "recall@5"))
    if recall is None or base_recall is None:
        failures.append("recall@5: missing candidate or baseline value")
    elif recall < base_recall - limits["MAX_RECALL5_DROP"] - 1e-9:
        failures.append(f"recall@5 {recall:.3f} dropped {base_recall - recall:.3f} below the "
                        f"baseline {base_recall:.3f} (allowed drop "
                        f"{limits['MAX_RECALL5_DROP']:.3f})")

    faith = _metric(candidate, "end_to_end", "faithfulness")
    if faith is None:
        failures.append("faithfulness: the candidate run has no judged answers")
    elif faith < limits["MIN_FAITHFULNESS"] - 1e-9:
        failures.append(f"faithfulness {faith:.3f} is below the minimum "
                        f"{limits['MIN_FAITHFULNESS']:.3f}")

    p95 = _metric(candidate, "end_to_end", "latency_p95_seconds")
    if p95 is None:
        failures.append("p95 latency: missing candidate value")
    elif p95 > limits["MAX_P95_SECONDS"]:
        failures.append(f"p95 latency {p95:.2f}s exceeds the maximum "
                        f"{limits['MAX_P95_SECONDS']:.2f}s")

    abstain, base_abstain = (_metric(candidate, "end_to_end", "abstention_correctness"),
                             _metric(baseline, "end_to_end", "abstention_correctness"))
    if abstain is None or base_abstain is None:
        failures.append("abstention correctness: missing candidate or baseline value")
    elif abstain < base_abstain - limits["MIN_ABSTENTION_MARGIN"] - 1e-9:
        failures.append(f"abstention correctness {abstain:.3f} is lower than the baseline "
                        f"{base_abstain:.3f}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--thresholds", type=Path, required=True)
    args = parser.parse_args()
    try:
        limits = thresholds(args.thresholds)
        candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        failures = evaluate(candidate, baseline, limits)
    except (OSError, ValueError, TypeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    print(f"thresholds: {json.dumps(limits)}")
    print(f"candidate:  {args.candidate} ({candidate.get('serving', {}).get('collection_version')})")
    print(f"baseline:   {args.baseline} ({baseline.get('serving', {}).get('collection_version')})")
    if failures:
        print("RELEASE GATE: REJECT")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("RELEASE GATE: PASS (recall@5 drop, faithfulness, p95 latency and abstention "
          "all within thresholds)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
