#!/usr/bin/env python3
"""Recompute the component-level metrics of saved run_suite folders from their raw rows.

    python eval/rescore_component.py eval/results/a03/results/<stamp>-<label> [...]
    python eval/rescore_component.py --golden eval/golden.jsonl <folder> [...]

--golden re-reads each question's gold locations from the golden file before scoring, so a
corrected gold page applies to old runs too (the raw rows on disk keep what they had).

Used once on 25 Nov 2026 after fixing nDCG@5 (a gold page matched by two chunks was counted
twice, giving values above 1). It rewrites the component block of suite.json and summary.md;
the raw e2e-run-*.json and noise-run-*.json rows are not changed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.component_eval import delta, score  # noqa: E402
from eval.run_suite import mean_levels, summary_markdown  # noqa: E402


def refresh(rows: list[dict], gold: dict[str, list[dict]] | None) -> list[dict]:
    if gold is None:
        return rows
    return [{**row, "relevant": gold[row["id"]]} if row.get("id") in gold else row
            for row in rows]


def main() -> int:
    args = sys.argv[1:]
    gold = None
    note = "nDCG@5 dedup fix, 25 Nov 2026 (eval/rescore_component.py)"
    if args[:1] == ["--golden"]:
        from eval.run_eval import load_golden
        gold = {q["id"]: q["relevant"] for q in load_golden(Path(args[1]))}
        args = args[2:]
        note = ("nDCG@5 dedup fix and gold pages re-read from the corrected golden set, "
                "25 Nov 2026 (eval/rescore_component.py --golden)")
    for folder in map(Path, args):
        suite = json.loads((folder / "suite.json").read_text())
        for i, levels in enumerate(suite["runs"], 1):
            rows = refresh(json.loads((folder / f"e2e-run-{i}.json").read_text())["rows"], gold)
            noisy = refresh(json.loads((folder / f"noise-run-{i}.json").read_text())["rows"],
                            gold)
            clean, noise = score(rows), score(noisy)
            levels["component"] = {**clean,
                                   **{f"noise_{k}": v for k, v in noise.items() if k != "n_answerable"},
                                   **{f"noise_delta_{k}": v for k, v in delta(clean, noise).items()}}
        suite["mean"] = mean_levels(suite["runs"])
        if len(suite["runs"]) > 1:
            from eval.run_suite import flatten
            first, last = flatten(suite["runs"][0]), flatten(suite["runs"][-1])
            suite["difference_run1_run2"] = {k: round(abs(v - last[k]), 6)
                                             for k, v in first.items() if last.get(k) is not None}
        suite["rescored_component"] = note
        (folder / "suite.json").write_text(json.dumps(suite, indent=2) + "\n")
        (folder / "summary.md").write_text(summary_markdown(suite))
        print(folder.name, {k: suite["mean"]["component"][k] for k in ("recall@5", "mrr", "ndcg@5")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
