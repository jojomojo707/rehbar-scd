# baseline (chunk 480) vs candidate (chunk 384)

- **baseline (chunk 480)**: `20261125T120409Z-baseline`, collection `rahbar-v20261125-120258`, embedding `BAAI/bge-small-en-v1.5@aa8f8b060edb/onnx-sha256:51f1bd0addd6e859`, top_k `5`, 32 questions, 2 runs
- **candidate (chunk 384)**: `20261125T122353Z-candidate-chunk384`, collection `rahbar-candidate-v20261125-122317`, embedding `BAAI/bge-small-en-v1.5@aa8f8b060edb/onnx-sha256:51f1bd0addd6e859`, top_k `5`, 32 questions, 2 runs

| Level | Metric (mean of runs) | baseline (chunk 480) | candidate (chunk 384) | Change |
| --- | --- | ---: | ---: | ---: |
| module | paraphrase_mean_cosine | 0.8572 | 0.8572 | +0 |
| module | unrelated_mean_cosine | 0.5553 | 0.5553 | +0 |
| module | gap | 0.302 | 0.302 | +0 |
| module | embed_seconds_per_chunk_mean | 0.01221 | 0.01333 | +0.001117 |
| module | embed_seconds_per_chunk_p95 | 0.01498 | 0.01812 | +0.003149 |
| module | determinism_max_abs_diff | 0 | 0 | +0 |
| component | n_answerable | 27 | 27 | +0 |
| component | recall@3 | 0.6667 | 0.6667 | +0 |
| component | recall@5 | 0.6852 | 0.6852 | +0 |
| component | mrr | 0.6235 | 0.6235 | +0 |
| component | ndcg@5 | 0.6287 | 0.6287 | +0 |
| component | noise_recall@3 | 0.5926 | 0.5556 | -0.03704 |
| component | noise_recall@5 | 0.6111 | 0.6111 | +0 |
| component | noise_mrr | 0.5679 | 0.5463 | -0.0216 |
| component | noise_ndcg@5 | 0.5725 | 0.5563 | -0.01624 |
| component | noise_delta_recall@3 | -0.07407 | -0.1111 | -0.03704 |
| component | noise_delta_recall@5 | -0.07407 | -0.07407 | +0 |
| component | noise_delta_mrr | -0.05556 | -0.07716 | -0.0216 |
| component | noise_delta_ndcg@5 | -0.05621 | -0.07245 | -0.01624 |
| end_to_end | questions | 32 | 32 | +0 |
| end_to_end | abstention_correctness | 1 | 1 | +0 |
| end_to_end | answer_rate_answerable | 0.463 | 0.3519 | -0.1111 |
| end_to_end | citation_validity | 1 | 1 | +0 |
| end_to_end | e2e_recall@5 | 0.6481 | 0.6481 | +0 |
| end_to_end | fallbacks | 7 | 9 | +2 |
| end_to_end | cache_hits | 0 | 0 | +0 |
| end_to_end | latency_p50_seconds | 1.049 | 1.081 | +0.0315 |
| end_to_end | latency_p95_seconds | 10.51 | 9.934 | -0.578 |
| end_to_end | answered | 12.5 | 9.5 | -3 |
| end_to_end | judged | 12.5 | 9.5 | -3 |
| end_to_end | faithful | 12.5 | 9 | -3.5 |
| end_to_end | faithfulness | 1 | 0.9583 | -0.04167 |
| end_to_end | human_labelled | 0 | 0 | +0 |

Release gate on candidate (chunk 384): **PASS**
