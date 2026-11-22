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

## Day 2 Minikube runs (2026-11-22)

The baseline run froze the live `rahbar` collection, the `BAAI/bge-small-en-v1.5` pin and `TOP_K=5`.
The candidate changed only `TOP_K` to 7. Both used the same 35-question JSONL suite and unchanged
corpus. The candidate passed the configurable gate against this same-cluster baseline; the previous
Assignment 02 baseline (`0.9375`) is not comparable because it used a different collection snapshot.

| Level / metric | Baseline (`101513Z`) | Candidate (`103422Z`) | Result |
| --- | ---: | ---: | --- |
| Module paraphrase mean cosine | 0.8572 | 0.8572 | unchanged |
| Module unrelated mean cosine | 0.5553 | 0.5553 | unchanged |
| Module mean gap | 0.3020 | 0.3020 | unchanged |
| Component recall@5 | 0.5000 | 0.5000 | unchanged |
| Component MRR | 0.4944 | 0.4944 | unchanged |
| End-to-end recall@5 | 0.5833 | 0.5833 | gate pass |
| Citation validity / abstention | 1.0 / 1.0 | 1.0 / 1.0 | unchanged |
| p95 latency / cache hits | 2.31s / 15 | 11.10s / 0 | cache states differ; no cold-latency claim |
| Fallback count | 4 | 8 | observed increase; not attributed to TOP_K because provider/cache state differs |

The `TOP_K` change did not improve recall or component ranking, so it has no measured retrieval
benefit in this experiment. It met the guardrails and was briefly rolled out to the API Deployment,
then rolled back; post-rollback trace `68463cbd37164cdb8a9cc208fa676af2` records the restored model
pin and `rahbar-v20261106-192510` collection. The full comparison is
`eval/results/day2-20261122/20261122T103706Z-comparison.md`.

The Batch B ingestion Job verified 8 documents and embedded 17 chunks into the isolated
`rahbar-day2-batch-b-v20261122-101850` collection. The Chroma collection count was 17, matching
the per-document report. The 35-question run against this Batch B-only collection recorded
end-to-end recall@5 `0.2333` (baseline `0.5833`), component recall@5 `0.2333` (baseline `0.5000`),
and the same module means above; the gate rejected it. This deliberately shows data drift degrading
retrieval while the embedding module stays fixed. Raw files and the 35 query traces are in
`eval/results/day2-20261122/` and `traces/day2-20261122/`.

The 40-query coverage rerun retained threshold `0.65`: 28 in-scope queries had minimum similarity
`0.7057` and zero remained uncovered; 2 of 12 out-of-scope queries exceeded the threshold. Running
the intentionally strict `0.99` threshold exited 1 and grouped the newly uncovered topics. See
`eval/results/day2-coverage-after.json` and `eval/results/day2-coverage-fail-demo.json`.

`release-gate.py` reads recall drop, faithfulness floor, p95 ceiling and abstention against the
frozen baseline. ConfigMap values are `0.05`, `0.90`, `15s`, and “no worse than baseline”. On the
saved candidate, the committed threshold passed; changing only `MAX_P95_SECONDS` to `0.001` rejected
it; restoring `15` passed again without rebuilding. Evidence: `docs/evidence/day2-gate-outcomes.txt`.

## Initial Kubernetes resource estimates

See [Kubernetes estimates and commands](../k8s/README.md#initial-job-resource-estimates). Values
are initial estimates; only actual Day 2 Job measurements can establish tuned limits.
