# Assignment 03 evaluation suite 20261121T191231Z

Seed: `20261122`

## End-to-end metrics

| Metric | Run 1 | Run 2 | Absolute difference |
| --- | ---: | ---: | ---: |
| recall@3 | 0.5666666666666667 | 0.5666666666666667 | 0.0 |
| recall@5 | 0.5833333333333334 | 0.5833333333333334 | 0.0 |
| citation_validity | 1.0 | 1.0 | 0.0 |
| abstention_correctness | 1.0 | 1.0 | 0.0 |

## Retrieval component metrics

| Metric | Run 1 | Run 2 | Absolute difference |
| --- | ---: | ---: | ---: |
| recall@3 | 0.48333333333333334 | 0.48333333333333334 | 0.0 |
| recall@5 | 0.5 | 0.5 | 0.0 |
| mrr | 0.49444444444444446 | 0.49444444444444446 | 0.0 |
| ndcg@5 | 0.48568805729851067 | 0.48568805729851067 | 0.0 |

## Latency

| Metric (seconds) | Run 1 | Run 2 | Absolute difference |
| --- | ---: | ---: | ---: |
| latency_p50_seconds | 2.39 | 1.03 | 1.36 |
| latency_p95_seconds | 11.57 | 9.04 | 2.53 |

Manual trace faithfulness sample: 100.0% (8 reviewed; partner confirmation pending).

## Gate outcomes

- Run 1: recall@5 0.583 is more than 5% below the baseline 0.938
- Run 2: recall@5 0.583 is more than 5% below the baseline 0.938

Run 2 has semantic-cache hits; latency is not a cold-run comparison. Model/provider and retrieval tie-breaking can also vary.

Raw module, API and component results are in this directory.
