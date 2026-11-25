# Assignment 03 evaluation data

## Golden set

`golden.jsonl` has 26 cases: 16 answerable, five unanswerable and five hard. It carries the existing Assignment 02 team's 18 cases forward (16 grounded/injection questions and two hostel abstention questions) and adds three hostel abstentions plus five harder multi-clause/version cases. The prior 18 retain their `human` origin and provenance; the eight new cases are labeled `synthetic`.

Each answerable case has a concise expected answer and one or more `{document, page, section}` gold locations. PDF pages are 1-based physical page numbers, matching `Page.page` in the extraction pipeline; HTML pages use page 1. Unanswerable cases have `must_abstain: true`, an empty gold list and no expected answer. Hard cases can have multiple gold locations.

The eight synthetic cases have a manual-review note documenting their source-scope or answer/location check. The source was checked against the files listed in `corpus/MANIFEST.md`; intentionally absent hostel material is documented in `docs/CORPUS.md`. Run the structural/count check with:

```powershell
python eval/validate_assignment_sets.py
```

## Embedding module benchmark

`module_pairs.json` supplies 15 paraphrase and 15 unrelated pairs. The benchmark uses the pinned `BAAI/bge-small-en-v1.5` FastEmbed model and records the seed, hardware/runtime versions, model-file digest, pairwise cosine values, warm per-chunk latency and repeated-text determinism difference.

Run it with the repository virtual environment after installing `indexer/requirements.txt`:

```powershell
.venv\Scripts\python.exe eval/run_module_eval.py
```

It writes the raw results to `eval/results/module-eval.json` and the concise summary to `eval/results/module-eval.md`. Timing measures one passage per call after model initialization and a warmup, with `batch_size=1`; it is a local CPU benchmark, not a production latency claim. Use the same model, runtime, thread count and seed for comparisons.
