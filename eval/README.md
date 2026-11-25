# Evaluation (Assignment 03, Parts B to E)

All commands run from the repository root with the root `.venv`. On the cluster the same code
runs in the `rahbar-evaluator` image through `k8s/eval-job.yaml`.

## Data

| File | What it is |
| --- | --- |
| `golden.jsonl` | 47 questions: 32 used for the Part B/C runs (16 answerable, 5 unanswerable, 11 hard, of which 6 come from Batch B) plus 15 E4 additions. Fields: `id, bucket, question, answerable, gold_answer, gold[{document, page, section}], origin (human/synthetic), authored_by, manual_review` |
| `module_pairs.json` | 15 paraphrase and 15 unrelated sentence pairs for the embedding module test |
| `coverage_queries.jsonl` | 40 live-style queries: 28 in the golden-set domain, 12 on topics the corpus does not cover |
| `batches/` | Batch B (12 planted documents), the one-line update used for the changed-document demo, and `expected-dispositions.json` |
| `human_labels.json` | hand labels of answers (created by `label_answers.py`) |
| `results/a03/` | every result of the submitted runs (see below) |

## Commands

```bash
python eval/validate_assignment_sets.py            # golden-set counts and >= 8 hand-reviewed synthetic cases
python eval/review_synthetic.py                    # hand-review pending synthetic questions (records your name)
python eval/run_suite.py --api http://<api> --label <name> --trace-dir <traces> [--baseline <suite.json> --thresholds k8s/base/release-gate-configmap.yaml]
python eval/compare_runs.py --before <a>/suite.json --after <b>/suite.json --out <file.md>
python eval/release_gate.py --candidate <c>/suite.json --baseline <b>/suite.json --thresholds k8s/base/release-gate-configmap.yaml
python eval/label_answers.py --run eval/results/a03/results/<stamp>-baseline --count 10   # hand labels + judge agreement
python eval/trace.py trace <trace-id> --trace-dir traces/a03 [--brief]
python eval/trace.py summary --since <iso> --until <iso> --trace-dir traces/a03
python eval/coverage.py --out eval/results/a03/coverage-<name>.json     # exit 1 below 85 percent
```

`run_suite.py` sends every question with `Cache-Control: no-cache`, ranks the typo-noise queries
through `POST /api/retrieve` (no LLM call), judges faithfulness with `judge.py` against each
answer's traced context, and writes `<stamp>-<label>/` with `suite.json`, `summary.md`, one JSON
per run and level, and `to-label.json`. Exit 0 = ran (and gate passed), 1 = gate rejected,
2 = could not run. `EVAL_RUNS` and `EVAL_PAUSE` set repetitions and pacing (the free-tier hosted
LLM allows 8,000 tokens per minute and 200,000 per day).

## Submitted results (`results/a03/`)

| Folder / file | Run |
| --- | --- |
| `results/20261125T120409Z-baseline/` | Part B baseline: live API, collection `rahbar-v20261125-120258`, chunk 480, 2 runs |
| `results/20261125T122353Z-candidate-chunk384/` | C1 candidate: collection `rahbar-candidate-v20261125-122317`, chunk 384; gate PASS |
| `results/20261125T123327Z-candidate-topk1-bad/` | deliberately bad candidate (TOP_K=1); gate REJECT |
| `results/*-drift-batch-b/` | E3: live API after Batch B ingestion |
| `results/verification/` | one verification report per ingestion run (Part A) |
| `C1-comparison-chunk480-vs-384.md`, `E3-*` | level-by-level comparisons |
| `coverage-before.json`, `coverage-after.json`, `coverage-fail-demo.json` | Part E |
| `D3-trace-summary-*.json` | trace metrics over a time window |
