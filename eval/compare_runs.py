#!/usr/bin/env python3
"""Write a timestamped comparison for baseline and candidate three-level run artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def compare(baseline: dict, candidate: dict, metrics: tuple[str, ...]) -> dict:
    result = {}
    for metric in metrics:
        before, after = baseline.get(metric), candidate.get(metric)
        result[metric] = {
            "baseline": before,
            "candidate": after,
            "delta_candidate_minus_baseline": (round(float(after) - float(before), 8)
                                               if before is not None and after is not None else None),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-api", type=Path, required=True)
    parser.add_argument("--candidate-api", type=Path, required=True)
    parser.add_argument("--baseline-component", type=Path, required=True)
    parser.add_argument("--candidate-component", type=Path, required=True)
    parser.add_argument("--baseline-module", type=Path, required=True)
    parser.add_argument("--candidate-module", type=Path, required=True)
    parser.add_argument("--change", required=True, help="the single intentionally varied parameter")
    parser.add_argument("--gate-result", choices=("PASS", "REJECT"), required=True)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).with_name("results"))
    args = parser.parse_args()
    try:
        base_api, candidate_api = load(args.baseline_api), load(args.candidate_api)
        base_component, candidate_component = load(args.baseline_component), load(args.candidate_component)
        base_module, candidate_module = load(args.baseline_module), load(args.candidate_module)
        api_metrics = compare(base_api, candidate_api, (
            "recall@3", "recall@5", "citation_validity", "abstention_correctness",
            "latency_p50_seconds", "latency_p95_seconds", "cache_hits", "fallbacks",
        ))
        component_metrics = compare(base_component.get("baseline", {}),
                                    candidate_component.get("baseline", {}),
                                    ("recall@3", "recall@5", "mrr", "ndcg@5"))
        base_similarity, candidate_similarity = (base_module.get("semantic_similarity", {}),
                                                  candidate_module.get("semantic_similarity", {}))
        module_metrics = compare(base_similarity, candidate_similarity, (
            "paraphrase_mean_cosine", "unrelated_mean_cosine", "mean_gap_paraphrase_minus_unrelated",
        ))
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        parser.error(str(exc))

    created = datetime.now(timezone.utc)
    stamp = created.strftime("%Y%m%dT%H%M%SZ")
    report = {
        "schema_version": 1,
        "created_at": created.isoformat(),
        "controlled_change": args.change,
        "gate_result": args.gate_result,
        "baseline_files": {"api": str(args.baseline_api), "component": str(args.baseline_component),
                           "module": str(args.baseline_module)},
        "candidate_files": {"api": str(args.candidate_api), "component": str(args.candidate_component),
                            "module": str(args.candidate_module)},
        "api": api_metrics,
        "retrieval_component": component_metrics,
        "embedding_module": module_metrics,
        "notes": [
            "Module metrics should remain unchanged because the embedding model and module are not the varied parameter.",
            "Latency comparisons are cache-sensitive; inspect cache_hits and use cold runs before making a latency claim.",
        ],
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / f"{stamp}-comparison.json"
    md_path = args.out_dir / f"{stamp}-comparison.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = [f"# Controlled evaluation comparison {stamp}", "", f"Change: {args.change}",
             f"Release gate: **{args.gate_result}**", "",
             "| Level | Metric | Baseline | Candidate | Delta |", "| --- | --- | ---: | ---: | ---: |"]
    for level, values in (("End to end", api_metrics), ("Retrieval component", component_metrics),
                          ("Embedding module", module_metrics)):
        for metric, row in values.items():
            lines.append(f"| {level} | {metric} | {row['baseline']} | {row['candidate']} | "
                         f"{row['delta_candidate_minus_baseline']} |")
    lines += ["", "## Interpretation", "",
              "Read the metric changes against the single controlled change above. Module similarity "
              "should remain stable when the embedding model is held fixed. p95 latency is cache-sensitive; "
              "do not interpret the p95 delta as a cold-start performance comparison unless cache state "
              "is controlled.", ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {json_path} and {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
