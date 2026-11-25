# Assignment 03 Day 1 evaluation findings

## Current measured suite

- Golden set: 35 cases (25 answerable, 5 unanswerable, 5 hard), including 9 new Batch B policy cases.
- Both complete runs used seed `20261122`, FastEmbed `BAAI/bge-small-en-v1.5`, and the Minikube API.
- Embedding module: paraphrase cosine 0.857224, unrelated cosine 0.555263, gap 0.301961; same-text output was deterministic (max component difference 0).
- Retrieval component: recall@3 0.4833, recall@5 0.5000, MRR 0.4944, nDCG@5 0.4857.
- With three synthetic irrelevant candidates prepended: recall@3 0.0000, recall@5 0.4667, MRR 0.1233, nDCG@5 0.2033.
- End to end: recall@5 0.5833, citation validity 1.0000, abstention correctness 1.0000, p50 2.39s and p95 11.57s in run 1. Run 2 had more cache hits, so its lower p50/p95 is not a cold comparison.
- The gate failed both times because recall@5 0.5833 is below the saved 0.9375 baseline. This is retained as a failure. The active index is `rahbar-v20261106-192510`; new Batch B documents remain fixtures and were not added to this shared collection. Some hard cases also have incomplete exact source/page recall.
- Eight answerable outputs were compared manually with their retrieved contexts (faithfulness 8/8); the other team member still needs to confirm the review.

## Coverage before/after

With the pinned model and the same 0.65 cosine threshold, the 40 simulated queries had five in-scope misses before expanding the golden set and none after nine reviewed questions were added. Two out-of-scope queries still exceeded the threshold (16.7% false-positive rate); treat coverage as a review signal, not an answerability guarantee. Setting threshold 1.0 gives exit code 1 and records uncovered topics, proving the failure behavior.

Raw JSON and per-query rows are in `eval/results/20261121T191231Z/`; coverage files are adjacent under `eval/results/`.
