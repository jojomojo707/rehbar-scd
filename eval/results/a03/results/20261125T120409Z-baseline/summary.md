# Part B suite `20261125T120409Z` (baseline)

API `http://api:8000` | collection `rahbar-v20261125-120258` | embedding `BAAI/bge-small-en-v1.5@aa8f8b060edb/onnx-sha256:51f1bd0addd6e859` | seed `20261125` | golden `/app/eval/golden.jsonl` (32 questions)

| Level | Metric | Run 1 | Run 2 | Abs. difference |
| --- | --- | ---: | ---: | ---: |
| module | paraphrase_mean_cosine | 0.8572 | 0.8572 | 0 |
| module | unrelated_mean_cosine | 0.5553 | 0.5553 | 0 |
| module | gap | 0.302 | 0.302 | 0 |
| module | embed_seconds_per_chunk_mean | 0.01204 | 0.01238 | 0.0003347 |
| module | embed_seconds_per_chunk_p95 | 0.01496 | 0.015 | 3.998e-05 |
| module | determinism_max_abs_diff | 0 | 0 | 0 |
| component | n_answerable | 27 | 27 | 0 |
| component | recall@3 | 0.6111 | 0.6111 | 0 |
| component | recall@5 | 0.6296 | 0.6296 | 0 |
| component | mrr | 0.5802 | 0.5802 | 0 |
| component | ndcg@5 | 0.5725 | 0.5725 | 0 |
| component | noise_recall@3 | 0.537 | 0.537 | 0 |
| component | noise_recall@5 | 0.5556 | 0.5556 | 0 |
| component | noise_mrr | 0.537 | 0.537 | 0 |
| component | noise_ndcg@5 | 0.529 | 0.529 | 0 |
| component | noise_delta_recall@3 | -0.07407 | -0.07407 | 0 |
| component | noise_delta_recall@5 | -0.07407 | -0.07407 | 0 |
| component | noise_delta_mrr | -0.04321 | -0.04321 | 0 |
| component | noise_delta_ndcg@5 | -0.04354 | -0.04354 | 0 |
| end_to_end | questions | 32 | 32 | 0 |
| end_to_end | abstention_correctness | 1 | 1 | 0 |
| end_to_end | answer_rate_answerable | 0.4815 | 0.4444 | 0.03704 |
| end_to_end | citation_validity | 1 | 1 | 0 |
| end_to_end | e2e_recall@5 | 0.6481 | 0.6481 | 0 |
| end_to_end | fallbacks | 6 | 8 | 2 |
| end_to_end | cache_hits | 0 | 0 | 0 |
| end_to_end | latency_p50_seconds | 0.998 | 1.1 | 0.102 |
| end_to_end | latency_p95_seconds | 10.52 | 10.5 | 0.016 |
| end_to_end | answered | 13 | 12 | 1 |
| end_to_end | judged | 13 | 12 | 1 |
| end_to_end | faithful | 13 | 12 | 1 |
| end_to_end | faithfulness | 1 | 1 | 0 |
| end_to_end | human_labelled | 0 | 0 | 0 |

Noise test = the same golden questions with seeded typos (`noise_*` = noisy value, `noise_delta_*` = noisy minus clean).
Faithfulness = share of answered questions the judge found fully supported by the context recorded in their trace.
