# Part B suite `20261125T130413Z` (drift-batch-b)

API `http://api:8000` | collection `rahbar-v20261125-130024` | embedding `BAAI/bge-small-en-v1.5@aa8f8b060edb/onnx-sha256:51f1bd0addd6e859` | seed `20261125` | golden `/app/eval/golden.jsonl` (47 questions)

| Level | Metric | Run 1 |
| --- | --- | ---: |
| module | paraphrase_mean_cosine | 0.8572 |
| module | unrelated_mean_cosine | 0.5553 |
| module | gap | 0.302 |
| module | embed_seconds_per_chunk_mean | 0.01306 |
| module | embed_seconds_per_chunk_p95 | 0.01588 |
| module | determinism_max_abs_diff | 0 |
| component | n_answerable | 34 |
| component | recall@3 | 0.8235 |
| component | recall@5 | 0.8676 |
| component | mrr | 0.7412 |
| component | ndcg@5 | 0.7645 |
| component | noise_recall@3 | 0.7353 |
| component | noise_recall@5 | 0.8088 |
| component | noise_mrr | 0.6946 |
| component | noise_ndcg@5 | 0.7178 |
| component | noise_delta_recall@3 | -0.08823 |
| component | noise_delta_recall@5 | -0.05882 |
| component | noise_delta_mrr | -0.04657 |
| component | noise_delta_ndcg@5 | -0.04668 |
| end_to_end | questions | 47 |
| end_to_end | abstention_correctness | 1 |
| end_to_end | answer_rate_answerable | 0.02941 |
| end_to_end | citation_validity | 1 |
| end_to_end | e2e_recall@5 | 0.8382 |
| end_to_end | fallbacks | 29 |
| end_to_end | cache_hits | 0 |
| end_to_end | latency_p50_seconds | 10.55 |
| end_to_end | latency_p95_seconds | 14.83 |
| end_to_end | answered | 1 |
| end_to_end | judged | 1 |
| end_to_end | faithful | 1 |
| end_to_end | faithfulness | 1 |
| end_to_end | human_labelled | 0 |

**Release gate: REJECT**

- p95 latency 14.83s exceeds the maximum 12.00s

Noise test = the same golden questions with seeded typos (`noise_*` = noisy value, `noise_delta_*` = noisy minus clean).
Faithfulness = share of answered questions the judge found fully supported by the context recorded in their trace.
