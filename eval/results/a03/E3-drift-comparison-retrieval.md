# baseline (Batch A) vs after Batch B

- **baseline (Batch A)**: `20261125T120409Z-baseline`, collection `rahbar-v20261125-120258`, embedding `BAAI/bge-small-en-v1.5@aa8f8b060edb/onnx-sha256:51f1bd0addd6e859`, top_k `5`, 32 questions, 2 runs
- **after Batch B**: `20261125T130413Z-drift-batch-b`, collection `rahbar-v20261125-130024`, embedding `BAAI/bge-small-en-v1.5@aa8f8b060edb/onnx-sha256:51f1bd0addd6e859`, top_k `5`, 32 questions, 1 runs

| Level | Metric (mean of runs) | baseline (Batch A) | after Batch B | Change |
| --- | --- | ---: | ---: | ---: |
| module | paraphrase_mean_cosine | 0.8572 | 0.8572 | +0 |
| module | unrelated_mean_cosine | 0.5553 | 0.5553 | +0 |
| module | gap | 0.302 | 0.302 | +0 |
| module | embed_seconds_per_chunk_mean | 0.01221 | 0.01306 | +0.000851 |
| module | embed_seconds_per_chunk_p95 | 0.01498 | 0.01588 | +0.000904 |
| module | determinism_max_abs_diff | 0 | 0 | +0 |
| component | n_answerable | 27 | 27 | +0 |
| component | recall@3 | 0.6667 | 0.8889 | +0.2222 |
| component | recall@5 | 0.6852 | 0.9074 | +0.2222 |
| component | mrr | 0.6235 | 0.821 | +0.1975 |
| component | ndcg@5 | 0.6287 | 0.8324 | +0.2037 |
| end_to_end | questions | 32 | 32 | +0 |
| end_to_end | abstention_correctness | 1 | 1 | +0 |
| end_to_end | answer_rate_answerable | 0.463 | 0.03704 | -0.4259 |
| end_to_end | citation_validity | 1 | 1 | +0 |
| end_to_end | e2e_recall@5 | 0.6481 | 0.8704 | +0.2222 |
| end_to_end | cache_hits | 0 | 0 | +0 |
| end_to_end | latency_p50_seconds | 1.049 | 10.59 | +9.54 |
| end_to_end | latency_p95_seconds | 10.51 | 12.9 | +2.393 |
| end_to_end | faithfulness | 1 | 1 | +0 |
| end_to_end | provider_or_validation_fallbacks | 7 | 22 | +15 |

Release gate on after Batch B: **REJECT**
- p95 latency 14.83s exceeds the maximum 12.00s
