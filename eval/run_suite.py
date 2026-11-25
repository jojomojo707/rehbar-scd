#!/usr/bin/env python3
"""Assignment 03 Part B: the whole offline test suite at three levels, in one command.

    python eval/run_suite.py --api http://api:8000 --label baseline \
        --trace-dir /pipeline-data/traces --out-dir /pipeline-data/eval/results

For each of --runs repetitions (default 2, same --seed):
  module      embedding: paraphrase vs unrelated cosine and gap, time per chunk, determinism
  component   retrieval: recall@3, recall@5, MRR, nDCG@5; noise test with seeded query typos
  end-to-end  answers: faithfulness (LLM judge over the traced context), abstention
              correctness, citation validity, latency p50/p95; judge agreement with hand labels

Every question is sent with Cache-Control: no-cache, so a repeat is a real repeat. Results go to
<out-dir>/<UTC stamp>-<label>/: suite.json, summary.md, one JSON per run and level, and
to-label.json (answers for hand labelling). With --baseline and --thresholds the release gate
(release_gate.py) runs at the end and the exit code is 1 when it rejects the candidate.
Exit 0 = suite ran (and gate passed), 1 = gate rejected, 2 = the suite could not run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from eval.component_eval import delta, score, typo_query  # noqa: E402
from eval.run_eval import citation_validity, load_golden, recall_at_k  # noqa: E402

FALLBACK_MARKER = "reliable, cited answer"


def ask(client: httpx.Client, api: str, question: str) -> tuple[dict, float]:
    started = time.perf_counter()
    for attempt in range(4):
        response = client.post(f"{api.rstrip('/')}/api/ask", json={"question": question},
                               headers={"Cache-Control": "no-cache"})
        if response.status_code in (429, 502, 503) and attempt < 3:
            time.sleep(5 * (attempt + 1))
            continue
        response.raise_for_status()
        break
    return response.json(), round(time.perf_counter() - started, 3)


def run_questions(client: httpx.Client, api: str, questions: list[dict], pause: float,
                  rewrite=None) -> list[dict]:  # type: ignore[no-untyped-def]
    rows = []
    for q in questions:
        asked = rewrite(q["question"]) if rewrite else q["question"]
        response, seconds = ask(client, api, asked)
        retrieved = response.get("retrieved") or []
        rows.append({
            "id": q["id"], "bucket": q.get("bucket"), "question": q["question"], "asked": asked,
            "must_abstain": q["must_abstain"], "relevant": q["relevant"],
            "request_id": response.get("request_id"), "seconds": seconds,
            "answer": response.get("answer", ""), "citations": response.get("citations") or [],
            "answered_from_context": bool(response.get("answered_from_context")),
            "fallback": FALLBACK_MARKER in str(response.get("answer", ""))
            and not response.get("citations"),
            "cached": bool(response.get("cached")),
            "retrieved": [{"source": r.get("source"), "section": r.get("section"),
                           "page": r.get("page"), "score": r.get("score"),
                           "chunk_id": r.get("chunk_id")} for r in retrieved],
            "citation_validity": citation_validity(response),
            "e2e_recall@5": recall_at_k(q["relevant"], retrieved, 5),
        })
        print(f"  {q['id']:<5} {seconds:6.2f}s  {'ABSTAIN' if not rows[-1]['answered_from_context'] else 'answer '}  {asked[:64]}", flush=True)
        if pause:
            time.sleep(pause)
    return rows


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, round((len(ordered) - 1) * p))], 3)


def load_traces(trace_dir: Path | None) -> dict[str, dict]:
    if not trace_dir or not trace_dir.is_dir():
        return {}
    from eval.trace import read_traces
    return {row["trace_id"]: row for row in read_traces(trace_dir)}


def answer_sha(row: dict) -> str:
    return hashlib.sha256(f"{row['id']}\n{row['answer']}".encode()).hexdigest()[:16]


def faithfulness(rows: list[dict], trace_dir: Path | None, use_judge: bool,
                 human: dict[str, bool]) -> dict[str, Any]:
    """Judge every answered question against the context its trace recorded."""
    answered = [r for r in rows if r["answered_from_context"] and not r["fallback"]]
    traces = load_traces(trace_dir)
    verdicts, agreement = [], []
    if use_judge:
        from eval.judge import judge
        with httpx.Client(timeout=90) as client:
            for row in answered:
                trace = traces.get(row["request_id"] or "")
                if trace is None:
                    row["faithfulness"] = {"faithful": None, "reason": "trace not found"}
                    continue
                context = trace.get("retrieved") or []
                row["context"] = [{"document": p.get("document"), "section": p.get("section"),
                                   "page": p.get("page"), "text": p.get("text")} for p in context]
                row["faithfulness"] = judge(row["question"], row["answer"], context, client)
                verdicts.append(row["faithfulness"]["faithful"])
                time.sleep(1.0)
    for row in answered:
        label = human.get(answer_sha(row))
        judged = (row.get("faithfulness") or {}).get("faithful")
        if label is not None and judged is not None:
            agreement.append(label == judged)
    return {
        "answered": len(answered), "judged": len(verdicts),
        "faithful": sum(verdicts),
        "faithfulness": round(sum(verdicts) / len(verdicts), 6) if verdicts else None,
        "judge_model": "openai/gpt-oss-120b" if use_judge else None,
        "human_labelled": len(agreement),
        "judge_human_agreement": round(sum(agreement) / len(agreement), 6) if agreement else None,
    }


def end_to_end(rows: list[dict]) -> dict[str, Any]:
    abstain = [not r["answered_from_context"] for r in rows if r["must_abstain"]]
    answerable = [r for r in rows if not r["must_abstain"]]
    cites = [(r["citation_validity"], len(r["citations"])) for r in rows
             if r["citation_validity"] is not None]
    seconds = [r["seconds"] for r in rows]
    return {
        "questions": len(rows),
        "abstention_correctness": round(sum(abstain) / len(abstain), 6) if abstain else None,
        "answer_rate_answerable": round(sum(r["answered_from_context"] for r in answerable)
                                        / len(answerable), 6) if answerable else None,
        "citation_validity": round(sum(v * n for v, n in cites) / sum(n for _, n in cites), 6)
        if cites else None,
        "e2e_recall@5": round(statistics.fmean(r["e2e_recall@5"] for r in rows
                                               if r["e2e_recall@5"] is not None), 6),
        "fallbacks": sum(r["fallback"] for r in rows),
        "cache_hits": sum(r["cached"] for r in rows),
        "latency_p50_seconds": percentile(seconds, .50),
        "latency_p95_seconds": percentile(seconds, .95),
    }


def module_level(args: argparse.Namespace, out: Path, run: int) -> dict:
    from eval.run_module_eval import run as run_module

    result = run_module(argparse.Namespace(pairs=args.pairs, cache_dir=args.cache_dir,
                                           model=args.model, seed=args.seed, threads=1))
    (out / f"module-run-{run}.json").write_text(json.dumps(result, indent=2) + "\n")
    sim, timing = result["semantic_similarity"], result["per_chunk_embedding_time"]
    return {"paraphrase_mean_cosine": sim["paraphrase_mean_cosine"],
            "unrelated_mean_cosine": sim["unrelated_mean_cosine"],
            "gap": sim["mean_gap_paraphrase_minus_unrelated"],
            "embed_seconds_per_chunk_mean": timing["mean_seconds"],
            "embed_seconds_per_chunk_p95": timing["p95_seconds"],
            "determinism_max_abs_diff": result["same_text_determinism"][
                "max_absolute_component_difference"]}


def flatten(levels: dict[str, dict]) -> dict[str, float]:
    flat = {}
    for level, values in levels.items():
        for key, value in values.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                flat[f"{level}.{key}"] = value
    return flat


def mean_levels(runs: list[dict[str, dict]]) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for level in runs[0]:
        merged[level] = {}
        for key, value in runs[0][level].items():
            values = [r[level].get(key) for r in runs]
            if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
                merged[level][key] = round(statistics.fmean(values), 6)  # type: ignore[arg-type]
            else:
                merged[level][key] = value
    return merged


def summary_markdown(result: dict) -> str:
    runs = result["runs"]
    flat = [flatten(r) for r in runs]
    lines = [f"# Part B suite `{result['stamp']}` ({result['label']})", "",
             f"API `{result['api']}` | collection `{result['serving'].get('collection_version')}` "
             f"| embedding `{result['serving'].get('embedding_version')}` | seed `{result['seed']}`"
             f" | golden `{result['golden']}` ({result['questions']} questions)", "",
             "| Level | Metric | " + " | ".join(f"Run {i + 1}" for i in range(len(runs)))
             + (" | Abs. difference |" if len(runs) > 1 else " |"),
             "| --- | --- | " + " | ".join("---:" for _ in runs)
             + (" | ---: |" if len(runs) > 1 else " |")]
    for key in flat[0]:
        level, metric = key.split(".", 1)
        values = [f.get(key) for f in flat]
        cells = " | ".join("n/a" if v is None else f"{v:.4g}" for v in values)
        diff = ""
        if len(runs) > 1 and None not in values:
            diff = f" | {abs(values[0] - values[-1]):.4g}"  # type: ignore[operator]
        lines.append(f"| {level} | {metric} | {cells}{diff} |")
    gate = result.get("gate")
    if gate:
        lines += ["", f"**Release gate: {gate['decision']}**", ""]
        lines += [f"- {reason}" for reason in gate["failures"]] or ["- all thresholds met"]
    lines += ["", "Noise test = the same golden questions with seeded typos "
              "(`noise_*` = noisy value, `noise_delta_*` = noisy minus clean).",
              "Faithfulness = share of answered questions the judge found fully supported by "
              "the context recorded in their trace."]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", required=True)
    parser.add_argument("--label", default="run")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.jsonl")
    parser.add_argument("--pairs", type=Path, default=HERE / "module_pairs.json")
    parser.add_argument("--out-dir", type=Path, default=HERE / "results")
    parser.add_argument("--trace-dir", type=Path, default=None,
                        help="the API's trace JSONL directory (judge context)")
    parser.add_argument("--human-labels", type=Path, default=HERE / "human_labels.json")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20261125)
    parser.add_argument("--pause", type=float, default=0.5)
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=Path("/models"))
    parser.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--baseline", type=Path, help="baseline suite.json for the gate")
    parser.add_argument("--thresholds", type=Path, help="gate ConfigMap dir or YAML")
    args = parser.parse_args()

    questions = load_golden(args.golden)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out_dir / f"{stamp}-{args.label}"
    out.mkdir(parents=True, exist_ok=True)
    human: dict[str, bool] = {}
    if args.human_labels.is_file():
        for label in json.loads(args.human_labels.read_text()).get("labels", []):
            human[label["answer_sha"]] = bool(label["faithful"])

    runs, serving = [], {}
    try:
        with httpx.Client(timeout=180) as client:
            for run in range(1, args.runs + 1):
                print(f"== run {run}/{args.runs}: end-to-end ({len(questions)} questions)")
                rows = run_questions(client, args.api, questions, args.pause)
                print(f"== run {run}: component noise test (typos, seed {args.seed})")
                rng = random.Random(args.seed)
                answerable = [q for q in questions if not q["must_abstain"]]
                noisy = run_questions(client, args.api, answerable, args.pause,
                                      rewrite=lambda text: typo_query(text, rng))
                faith = faithfulness(rows, args.trace_dir, not args.no_judge, human)
                traces = load_traces(args.trace_dir)
                first = traces.get(rows[0]["request_id"] or "", {})
                serving = serving or {k: first.get(k) for k in (
                    "collection", "collection_version", "embedding_model", "embedding_version",
                    "model_parameters")}
                clean_c, noisy_c = score(rows), score(noisy)
                component = {**clean_c,
                             **{f"noise_{k}": v for k, v in noisy_c.items() if k != "n_answerable"},
                             **{f"noise_delta_{k}": v for k, v in delta(clean_c, noisy_c).items()}}
                levels = {"module": module_level(args, out, run), "component": component,
                          "end_to_end": {**end_to_end(rows), **faith}}
                runs.append(levels)
                (out / f"e2e-run-{run}.json").write_text(json.dumps(
                    {"levels": levels, "rows": rows}, indent=2) + "\n")
                (out / f"noise-run-{run}.json").write_text(json.dumps({"rows": noisy}, indent=2))
                if run == 1:
                    sheet = [{"id": r["id"], "answer_sha": answer_sha(r), "question": r["question"],
                              "answer": r["answer"], "context": r.get("context", []),
                              "faithful": None, "labeller": ""}
                             for r in rows if r["answered_from_context"] and not r["fallback"]]
                    (out / "to-label.json").write_text(json.dumps(sheet, indent=2) + "\n")
    except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
        print(f"suite could not run: {exc}", file=sys.stderr)
        return 2

    result: dict[str, Any] = {
        "stamp": stamp, "label": args.label, "api": args.api, "seed": args.seed,
        "golden": str(args.golden), "questions": len(questions), "serving": serving,
        "runs": runs, "mean": mean_levels(runs),
        "difference_run1_run2": {k: round(abs(v - flatten(runs[-1])[k]), 6)
                                 for k, v in flatten(runs[0]).items()
                                 if flatten(runs[-1]).get(k) is not None} if len(runs) > 1 else {},
    }
    code = 0
    if args.baseline and args.thresholds:
        from eval.release_gate import evaluate, thresholds
        baseline = json.loads(args.baseline.read_text())
        failures = evaluate(result, baseline, thresholds(args.thresholds))
        result["gate"] = {"baseline": str(args.baseline), "failures": failures,
                          "thresholds": thresholds(args.thresholds),
                          "decision": "REJECT" if failures else "PASS"}
        code = 1 if failures else 0
    (out / "suite.json").write_text(json.dumps(result, indent=2) + "\n")
    (out / "summary.md").write_text(summary_markdown(result))
    print("\n" + summary_markdown(result))
    print(f"results: {out}")
    if "gate" in result:
        print(f"RELEASE GATE: {result['gate']['decision']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
