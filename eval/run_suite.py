#!/usr/bin/env python3
"""Run the pinned module benchmark and live API suite twice with one seed."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(command: list[str]) -> int:
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, check=False).returncode


def diff(values: list[dict], key: str) -> dict:
    first, second = values[0].get(key), values[1].get(key)
    return {"run_1": first, "run_2": second,
            "absolute_difference": round(abs(first - second), 8)
            if first is not None and second is not None else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True, help="running RAHBAR API base URL")
    parser.add_argument("--seed", type=int, default=20261121)
    parser.add_argument("--results-dir", type=Path, default=HERE / "results")
    parser.add_argument("--pause", type=float, default=0.0)
    parser.add_argument("--host")
    parser.add_argument("--reuse-existing-dir", type=Path,
                        help="rebuild summary from two completed runs without calling the API")
    args = parser.parse_args()
    if args.seed < 0 or args.pause < 0:
        parser.error("seed and pause must be non-negative")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = args.reuse_existing_dir or args.results_dir / stamp
    if args.reuse_existing_dir:
        stamp = outdir.name
        if not outdir.is_dir():
            parser.error(f"results directory does not exist: {outdir}")
    else:
        outdir.mkdir(parents=True, exist_ok=False)

    errors = []
    if not args.reuse_existing_dir:
        for index in (1, 2):
            module_json = outdir / f"module-run-{index}.json"
            module_md = outdir / f"module-run-{index}.md"
            code = run([sys.executable, str(HERE / "run_module_eval.py"), "--seed", str(args.seed),
                        "--out", str(module_json), "--report", str(module_md)])
            if code:
                errors.append(f"module run {index} exited {code}")

            api_json = outdir / f"api-run-{index}.json"
            command = [sys.executable, str(HERE / "run_eval.py"), "--api", args.api,
                       "--golden", str(HERE / "golden.jsonl"), "--out", str(api_json),
                       "--pause", str(args.pause)]
            if args.host:
                command.extend(["--host", args.host])
            code = run(command)
            if code not in (0, 1):
                errors.append(f"API run {index} exited {code}")
            code = run([sys.executable, str(HERE / "component_eval.py"), "--input", str(api_json),
                        "--out", str(outdir / f"component-run-{index}.json")])
            if code:
                errors.append(f"component run {index} exited {code}")

    try:
        module_results = [json.loads((outdir / f"module-run-{i}.json").read_text(encoding="utf-8")) for i in (1, 2)]
        api_results = [json.loads((outdir / f"api-run-{i}.json").read_text(encoding="utf-8")) for i in (1, 2)]
        component_results = [json.loads((outdir / f"component-run-{i}.json").read_text(encoding="utf-8")) for i in (1, 2)]
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"could not read completed run artifacts: {exc}")

    api_diff = {key: diff(api_results, key) for key in
                ("recall@3", "recall@5", "citation_validity", "abstention_correctness")}
    latency_diff = {key: diff(api_results, key) for key in
                    ("latency_p50_seconds", "latency_p95_seconds")}
    component_diff = {}
    for key in ("recall@3", "recall@5", "mrr", "ndcg@5"):
        component_diff[key] = diff([result["baseline"] for result in component_results], key)
    report = {
        "schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed, "api": args.api, "runs": 2,
        "api_metric_differences": api_diff,
        "component_metric_differences": component_diff,
        "latency_differences": latency_diff,
        "module_semantic_differences": {
            "paraphrase_mean_cosine": diff([r["semantic_similarity"] for r in module_results], "paraphrase_mean_cosine"),
            "unrelated_mean_cosine": diff([r["semantic_similarity"] for r in module_results], "unrelated_mean_cosine"),
        },
        "gate_results": [result.get("gate_failures", []) for result in api_results],
        "latency_note": "Run 2 has semantic-cache hits; latency is not a cold-run comparison. Model/provider and retrieval tie-breaking can also vary.",
        "errors": errors,
    }
    (outdir / "suite-summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = [f"# Assignment 03 evaluation suite {stamp}", "", f"Seed: `{args.seed}`", "",
             "## End-to-end metrics", "", "| Metric | Run 1 | Run 2 | Absolute difference |", "| --- | ---: | ---: | ---: |"]
    for key, values in api_diff.items():
        lines.append(f"| {key} | {values['run_1']} | {values['run_2']} | {values['absolute_difference']} |")
    lines += ["", "## Retrieval component metrics", "", "| Metric | Run 1 | Run 2 | Absolute difference |", "| --- | ---: | ---: | ---: |"]
    for key, values in component_diff.items():
        lines.append(f"| {key} | {values['run_1']} | {values['run_2']} | {values['absolute_difference']} |")
    lines += ["", "## Latency", "", "| Metric (seconds) | Run 1 | Run 2 | Absolute difference |", "| --- | ---: | ---: | ---: |"]
    for key, values in latency_diff.items():
        lines.append(f"| {key} | {values['run_1']} | {values['run_2']} | {values['absolute_difference']} |")
    faithfulness_file = HERE / "faithfulness_review_result.json"
    if faithfulness_file.exists():
        faithfulness = json.loads(faithfulness_file.read_text(encoding="utf-8"))
        report["faithfulness_review"] = {"score": faithfulness["score"], "n": faithfulness["n"],
                                         "reviewer": faithfulness["reviewer"]}
        lines += ["", f"Manual trace faithfulness sample: {faithfulness['score']:.1%} ({faithfulness['n']} reviewed; partner confirmation pending)."]
    lines += ["", "## Gate outcomes", ""]
    for index, failures in enumerate(report["gate_results"], start=1):
        lines.append(f"- Run {index}: " + ("; ".join(failures) if failures else "pass"))
    lines += ["", report["latency_note"], "", "Raw module, API and component results are in this directory."]
    (outdir / "suite-summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (outdir / "suite-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote timestamped suite summary to {outdir}")
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
