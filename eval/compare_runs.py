#!/usr/bin/env python3
"""Compare two Part B suite results level by level (C1 baseline vs candidate, E3 drift).

    python eval/compare_runs.py --before <dir>/suite.json --after <dir>/suite.json \
        --out eval/results/comparison-c1.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--before-name", default="baseline")
    parser.add_argument("--after-name", default="candidate")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    before = json.loads(args.before.read_text())
    after = json.loads(args.after.read_text())
    lines = [f"# {args.before_name} vs {args.after_name}", ""]
    for name, suite in ((args.before_name, before), (args.after_name, after)):
        serving = suite.get("serving", {})
        lines.append(f"- **{name}**: `{suite['stamp']}-{suite['label']}`, collection "
                     f"`{serving.get('collection_version')}`, embedding "
                     f"`{serving.get('embedding_version')}`, top_k "
                     f"`{(serving.get('model_parameters') or {}).get('top_k')}`, "
                     f"{suite['questions']} questions, {len(suite['runs'])} runs")
    lines += ["", f"| Level | Metric (mean of runs) | {args.before_name} | {args.after_name} | "
              "Change |", "| --- | --- | ---: | ---: | ---: |"]
    for level, values in after["mean"].items():
        for key, value in values.items():
            old = before["mean"].get(level, {}).get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            change = f"{value - old:+.4g}" if isinstance(old, (int, float)) else "n/a"
            old_text = f"{old:.4g}" if isinstance(old, (int, float)) else "n/a"
            lines.append(f"| {level} | {key} | {old_text} | {value:.4g} | {change} |")
    if after.get("gate"):
        lines += ["", f"Release gate on {args.after_name}: **{after['gate']['decision']}**"]
        lines += [f"- {reason}" for reason in after["gate"]["failures"]]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
