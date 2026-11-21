# Assignment 03 evaluation CLI

The labeled source is `golden.jsonl` (JSONL). It has 35 cases: 25 answerable (15+), 5
unanswerable, and 5 hard cases. Nine new cases were checked against the committed Batch B
policy documents; their one-page Markdown fixture locations use virtual page 1. `module_pairs.json`
contains the 15 paraphrase and 15 unrelated pairs.

## Stable commands

```powershell
python eval/run_suite.py --api http://127.0.0.1:8000 --seed 20261122 --pause 0
python eval/coverage.py --threshold 0.65 --out eval/results/coverage-after.json
python eval/trace.py summary --trace-dir docs/evidence/day1-traces
python eval/trace.py trace <trace-id> --trace-dir docs/evidence/day1-traces
```

`run_suite.py` performs the module benchmark, live API suite, component metrics and repeatability
comparison twice. It creates a UTC timestamp directory under `eval/results/` with each raw result,
component result, summary JSON/Markdown and difference table. `--reuse-existing-dir` rebuilds only
the summary from completed runs. Exit codes: 0 means both runs and report generation completed; 2
means invalid arguments or a subcommand could not produce its result. The API gate outcome is
recorded inside each result and may fail while the suite still completes.

`run_eval.py` supports `.yaml` and `.jsonl` inputs, records recall@3/5, citation validity,
abstention correctness, latency p50/p95, cache/fallback counts and each query result. Its exit codes
are 0 gate passed, 1 gate failed, and 2 invalid input. `component_eval.py` reports recall@3/5,
MRR and nDCG@5, then prepends three clearly labeled synthetic irrelevant candidates as a ranking
stress condition. `coverage.py` needs at least 28 in-scope and 12 out-of-scope examples; its
nonzero exit means at least one in-scope query is under the configured similarity threshold.

## Day 1 observed evaluation

Both fixed-seed runs completed on the running Minikube API. The module metrics were deterministic
(paraphrase mean cosine 0.857224, unrelated 0.555263, gap 0.301961); component and end-to-end
metric differences were zero. Run 2 had more cache hits, so its lower latency is not a cold-run
comparison. End-to-end recall@5 was 0.5833 versus the saved baseline 0.9375 and correctly failed
the gate. Batch B documents are fixtures and are not in the active 6-November collection; the
failed gate is recorded rather than presented as a pass. Citation validity and abstention
correctness were each 1.0. An eight-answer trace review measured 1.0 faithfulness; partner
confirmation is pending.

The controlled noise condition changed recall@3 from 0.4833 to 0, recall@5 from 0.5000 to 0.4667,
MRR from 0.4944 to 0.1233, and nDCG@5 from 0.4857 to 0.2033. These are a synthetic insertion
stress test, not a newly ingested corpus measurement.

## Initial Kubernetes resource estimates

See [Kubernetes estimates and commands](../k8s/README.md#initial-job-resource-estimates). Values
are initial estimates; only actual Day 2 Job measurements can establish tuned limits.
