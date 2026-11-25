#!/usr/bin/env python3
"""Compare two Part B suite results level by level (C1 baseline vs candidate, E3 drift).

    python eval/compare_runs.py --before <dir>/suite.json --after <dir>/suite.json \
        --out eval/results/comparison-c1.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def restrict(before_path: Path, before: dict, after_path: Path, after: dict) -> tuple[dict, dict]:
    """Recompute means over the questions both runs share (golden sets can differ, e.g. E3)."""
    from eval.component_eval import score
    from eval.run_suite import end_to_end

    def runs(path: Path) -> list[list[dict]]:
        return [json.loads(f.read_text())["rows"] for f in sorted(path.parent.glob("e2e-run-*.json"))]

    b_runs, a_runs = runs(before_path), runs(after_path)
    common = {r["id"] for r in b_runs[0]} & {r["id"] for r in a_runs[0]}

    def mean(rows_per_run: list[list[dict]], suite: dict) -> dict:
        levels = []
        for rows in rows_per_run:
            rows = [r for r in rows if r["id"] in common]
            answered = [r for r in rows if r["answered_from_context"] and not r["fallback"]]
            judged = [r["faithfulness"]["faithful"] for r in answered
                      if (r.get("faithfulness") or {}).get("faithful") is not None]
            e2e = end_to_end(rows)
            e2e["faithfulness"] = round(sum(judged) / len(judged), 6) if judged else None
            e2e["provider_or_validation_fallbacks"] = e2e.pop("fallbacks")
            levels.append({"module": suite["mean"]["module"], "component": score(rows),
                           "end_to_end": e2e})
        out: dict = {}
        for level in levels[0]:
            out[level] = {}
            for key, value in levels[0][level].items():
                values = [lv[level].get(key) for lv in levels]
                ok = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
                out[level][key] = round(statistics.fmean(values), 6) if ok else value
        return out

    before = {**before, "mean": mean(b_runs, before), "questions": len(common)}
    after = {**after, "mean": mean(a_runs, after), "questions": len(common)}
    return before, after


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--before-name", default="baseline")
    parser.add_argument("--after-name", default="candidate")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--common-ids", action="store_true",
                        help="recompute component and end-to-end metrics from the per-question "
                             "rows, using only question ids present in both runs")
    args = parser.parse_args()
    before = json.loads(args.before.read_text())
    after = json.loads(args.after.read_text())
    if args.common_ids:
        before, after = restrict(args.before, before, args.after, after)
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
