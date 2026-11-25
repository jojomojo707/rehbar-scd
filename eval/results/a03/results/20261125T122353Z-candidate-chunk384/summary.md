# Part B suite `20261125T122353Z` (candidate-chunk384)

API `http://api-candidate:8000` | collection `rahbar-candidate-v20261125-122317` | embedding `BAAI/bge-small-en-v1.5@aa8f8b060edb/onnx-sha256:51f1bd0addd6e859` | seed `20261125` | golden `/app/eval/golden.jsonl` (32 questions)

| Level | Metric | Run 1 | Run 2 | Abs. difference |
| --- | --- | ---: | ---: | ---: |
| module | paraphrase_mean_cosine | 0.8572 | 0.8572 | 0 |
| module | unrelated_mean_cosine | 0.5553 | 0.5553 | 0 |
| module | gap | 0.302 | 0.302 | 0 |
| module | embed_seconds_per_chunk_mean | 0.01269 | 0.01396 | 0.001266 |
| module | embed_seconds_per_chunk_p95 | 0.01526 | 0.02099 | 0.005732 |
| module | determinism_max_abs_diff | 0 | 0 | 0 |
| component | n_answerable | 27 | 27 | 0 |
| component | recall@3 | 0.6111 | 0.6111 | 0 |
| component | recall@5 | 0.6296 | 0.6296 | 0 |
| component | mrr | 0.5802 | 0.5802 | 0 |
| component | ndcg@5 | 0.5725 | 0.5725 | 0 |
| component | noise_recall@3 | 0.537 | 0.537 | 0 |
| component | noise_recall@5 | 0.5556 | 0.5556 | 0 |
| component | noise_mrr | 0.5185 | 0.5185 | 0 |
| component | noise_ndcg@5 | 0.5153 | 0.5153 | 0 |
| component | noise_delta_recall@3 | -0.07407 | -0.07407 | 0 |
| component | noise_delta_recall@5 | -0.07407 | -0.07407 | 0 |
| component | noise_delta_mrr | -0.06173 | -0.06173 | 0 |
| component | noise_delta_ndcg@5 | -0.05721 | -0.05721 | 0 |
| end_to_end | questions | 32 | 32 | 0 |
| end_to_end | abstention_correctness | 1 | 1 | 0 |
| end_to_end | answer_rate_answerable | 0.4444 | 0.2593 | 0.1852 |
| end_to_end | citation_validity | 1 | 1 | 0 |
| end_to_end | e2e_recall@5 | 0.6481 | 0.6481 | 0 |
| end_to_end | fallbacks | 7 | 11 | 4 |
| end_to_end | cache_hits | 0 | 0 | 0 |
| end_to_end | latency_p50_seconds | 1.165 | 0.996 | 0.169 |
| end_to_end | latency_p95_seconds | 10.47 | 9.397 | 1.074 |
| end_to_end | answered | 12 | 7 | 5 |
| end_to_end | judged | 12 | 7 | 5 |
| end_to_end | faithful | 11 | 7 | 4 |
| end_to_end | faithfulness | 0.9167 | 1 | 0.08333 |
| end_to_end | human_labelled | 0 | 0 | 0 |

**Release gate: PASS**

- all thresholds met

Noise test = the same golden questions with seeded typos (`noise_*` = noisy value, `noise_delta_*` = noisy minus clean).
Faithfulness = share of answered questions the judge found fully supported by the context recorded in their trace.
