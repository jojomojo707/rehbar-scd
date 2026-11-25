# F5 measured resource usage

`kubectl -n rahbar top pods --containers` every 10 s from 2026-11-25T11:49:49Z to 2026-11-25T13:15:13Z (UTC), covering
Batch A ingestion (OCR + 764 embeddings), the candidate ingestion (810 embeddings), the Batch B
and maintenance Jobs, four evaluation Jobs (two-run suites with the LLM judge), rollouts and the
idle API. Peaks are maxima over all pods of a workload; median is over all samples.

| Workload / container | samples | median CPU (m) | peak CPU (m) | median memory (Mi) | peak memory (Mi) |
| --- | ---: | ---: | ---: | ---: | ---: |
| api / api | 1670 | 3 | 676 | 260 | 478 |
| api-candidate / api | 672 | 3 | 1000 | 262 | 387 |
| candidate / indexer | 48 | 1998 | 2002 | 2556 | 2586 |
| chroma-0 / chroma | 511 | 2 | 46 | 137 | 412 |
| eval / evaluation | 249 | 1 | 50 | 30 | 410 |
| indexer / indexer | 57 | 2000 | 2001 | 1877 | 1886 |
| redis / redis | 511 | 7 | 11 | 29 | 38 |
| ui / ui | 499 | 1 | 1 | 3 | 11 |
