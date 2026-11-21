#!/usr/bin/env python3
"""Validate and summarize a manually reviewed trace faithfulness sample."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=Path(__file__).with_name("faithfulness_review.json"))
    parser.add_argument("--suite", type=Path, required=True)
    args = parser.parse_args()
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    result = json.loads(args.suite.read_text(encoding="utf-8"))
    available = {row["id"] for row in result.get("rows", [])}
    cases = labels.get("cases", [])
    missing = [case["id"] for case in cases if case["id"] not in available]
    if missing:
        parser.error(f"review labels do not match suite IDs: {missing}")
    score = sum(bool(case["faithful"]) for case in cases) / len(cases) if cases else None
    output = {"metric": "manual trace faithfulness sample", "score": score, "n": len(cases),
              "reviewer": labels["reviewer"], "rubric": labels["rubric"],
              "limitations": "Eight answerable outputs were manually compared with their saved retrieved context; reviewer is not yet partner-confirmed.",
              "cases": cases}
    args.labels.with_name("faithfulness_review_result.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in output.items() if k != "cases"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
