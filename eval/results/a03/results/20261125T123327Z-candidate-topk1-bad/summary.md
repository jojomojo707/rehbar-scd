# Part B suite `20261125T123327Z` (candidate-topk1-bad)

API `http://api-candidate:8000` | collection `rahbar-candidate-v20261125-122317` | embedding `BAAI/bge-small-en-v1.5@aa8f8b060edb/onnx-sha256:51f1bd0addd6e859` | seed `20261125` | golden `/app/eval/golden.jsonl` (32 questions)

| Level | Metric | Run 1 | Run 2 | Abs. difference |
| --- | --- | ---: | ---: | ---: |
| module | paraphrase_mean_cosine | 0.8572 | 0.8572 | 0 |
| module | unrelated_mean_cosine | 0.5553 | 0.5553 | 0 |
| module | gap | 0.302 | 0.302 | 0 |
| module | embed_seconds_per_chunk_mean | 0.01532 | 0.01346 | 0.001861 |
| module | embed_seconds_per_chunk_p95 | 0.0188 | 0.01603 | 0.002765 |
| module | determinism_max_abs_diff | 0 | 0 | 0 |
| component | n_answerable | 27 | 27 | 0 |
| component | recall@3 | 0.5 | 0.5 | 0 |
| component | recall@5 | 0.5 | 0.5 | 0 |
| component | mrr | 0.5185 | 0.5185 | 0 |
| component | ndcg@5 | 0.5042 | 0.5042 | 0 |
| component | noise_recall@3 | 0.4259 | 0.4259 | 0 |
| component | noise_recall@5 | 0.4259 | 0.4259 | 0 |
| component | noise_mrr | 0.4444 | 0.4444 | 0 |
| component | noise_ndcg@5 | 0.4301 | 0.4301 | 0 |
| component | noise_delta_recall@3 | -0.07407 | -0.07407 | 0 |
| component | noise_delta_recall@5 | -0.07407 | -0.07407 | 0 |
| component | noise_delta_mrr | -0.07408 | -0.07408 | 0 |
| component | noise_delta_ndcg@5 | -0.07407 | -0.07407 | 0 |
| end_to_end | questions | 32 | 32 | 0 |
| end_to_end | abstention_correctness | 1 | 1 | 0 |
| end_to_end | answer_rate_answerable | 0.5185 | 0.5185 | 0 |
| end_to_end | citation_validity | 1 | 1 | 0 |
| end_to_end | e2e_recall@5 | 0.5 | 0.5 | 0 |
| end_to_end | fallbacks | 0 | 0 | 0 |
| end_to_end | cache_hits | 0 | 0 | 0 |
| end_to_end | latency_p50_seconds | 0.803 | 0.795 | 0.008 |
| end_to_end | latency_p95_seconds | 1.195 | 1.194 | 0.001 |
| end_to_end | answered | 14 | 14 | 0 |
| end_to_end | judged | 14 | 14 | 0 |
| end_to_end | faithful | 14 | 13 | 1 |
| end_to_end | faithfulness | 1 | 0.9286 | 0.07143 |
| end_to_end | human_labelled | 0 | 0 | 0 |

**Release gate: REJECT**

- recall@5 0.500 dropped 0.130 below the baseline 0.630 (allowed drop 0.020)

Noise test = the same golden questions with seeded typos (`noise_*` = noisy value, `noise_delta_*` = noisy minus clean).
Faithfulness = share of answered questions the judge found fully supported by the context recorded in their trace.
