# Assignment 03 Day 1 baseline

Captured 2026-11-22 (PKT; 2026-11-21 UTC) before the remaining Day 1 implementation work.

## Repository and cluster

- Working branch: `b/golden-module-tests`
- Working commit: `005938023f51180a8099b00e673d4085f9d9c718`
- Current integration branch at baseline: `origin/dev` = `4b54405ef3cafb7251ca3818c7ecabef54f98538`
- Kubernetes context: `minikube`, Kubernetes `v1.37.0`; Minikube `v1.39.0`; Docker Engine `29.8.0`.
- The cluster was stopped at the start of this session. After `minikube start`, the existing Chroma StatefulSet and its PVC recovered; no PVC was deleted or recreated.
- Live API image: `rahbar-api:23f0ca6`; Chroma: `chromadb/chroma:1.0.12`; Redis: `redis:7.4.12-alpine`.
- Active index reported by `/readyz`: `rahbar-v20261106-192510`; embedding pin: `BAAI/bge-small-en-v1.5`, 384 dimensions.
- Existing PVCs: corpus 1 GiB, Chroma 2 GiB, Redis 1 GiB. No dedicated quarantine, archive, eval-results, or traces PVC/path was present.
- At the stabilized snapshot, Minikube used 877m CPU and 3686 MiB memory (47%). API pods used 245â€“272 MiB each; Chroma 49 MiB; Redis 12 MiB; UI 5 MiB. The existing HPA was at 8 replicas (min 3, max 8); it briefly reported high CPU during cold startup and later measured 2% of a 70% target.

## Baseline query

Question: â€œWhat language is used for instruction at FAST, apart from language and Islamic Studies courses?â€

- The first uncached `/api/ask` request completed in 30.8 seconds, answered from context, and logged `cached: false`.
- Answer: English.
- Citation: `academic-rules-handbook-jun-2026.pdf`, section 1.1, physical page 7; top similarity 0.7518453.
- The response was replayed from the semantic cache for capture; the replay returned the same citation with `cached: true`.

## Baseline checks

Commands were run in the repository's `.venv` using the Makefile's separate working directories:

| Suite | Result |
| --- | --- |
| Root `tests` | 12 passed |
| API tests with coverage gate | 144 passed; 91.89% coverage (60% required) |
| Indexer tests | 42 passed, 1 skipped |

The initial combined `pytest api/tests indexer/tests tests` invocation failed collection because the API and indexer require their own working-directory import roots; the Makefile's per-directory invocations above passed.
