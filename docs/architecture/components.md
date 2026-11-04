# Components

What each component owns, what it must never do, how its code is laid out, and what it depends on.
Data shapes live in [data-models.md](data-models.md), contracts in [interfaces.md](interfaces.md),
behaviour over time in [workflows.md](workflows.md).

Status words in the module tables:

- **given**: in the starter kit and unchanged
- **extend**: given, with additions
- **implement**: the starter left a stub to replace
- **new**: a file to create

## Component summary

| Component | Kubernetes object | Image | Owns | Depends on |
| --- | --- | --- | --- | --- |
| API | Deployment `api` | `rahbar-api` | Query pipeline, cache, turn log, readiness, metrics | chroma, redis, Groq, the embedding model in the image |
| Indexer | Job `indexer`, CronJob `reindex` | `rahbar-indexer` | Building and activating indexes | chroma, the corpus PVC, the embedding model in the image |
| Corpus fetcher | initContainer in the indexer pod | `rahbar-indexer` | Downloading and checking the corpus | nu.edu.pk, Google Drive, the committed manifest |
| UI | Deployment `ui` | `rahbar-ui` | The static chat page | None at runtime (the browser calls `/api`) |
| Chroma | StatefulSet `chroma` | `chromadb/chroma:1.0.12` | Vector storage | Its PVC |
| Redis | Deployment `redis` | `redis` (pinned 7.4 alpine tag) | Cache and turn log | Its PVC |
| Evaluation runner | Local and CI process | (none) | Scoring and gating | A live API |

## API

**Responsibility.** Answer one question per request through the eight steps of §3.2
([Query pipeline](workflows.md#query-pipeline)), and report whether the pod can serve
(`/readyz`).

**Must never:**

- write to Chroma (R-APP-01)
- index anything at start-up (−10)
- return a 5xx from `/api/ask` ([Error mapping](validation-and-errors.md#error-mapping))
- log the LLM key, the model's `reasoning`, or raw question text (default P3)

| Module | Responsibility | Status |
| --- | --- | --- |
| `app/main.py` | Start-up: settings, logging, embedder, retriever, provider, cache and turn-log clients, first index-state check. Request-id middleware. No indexing | extend |
| `app/config.py` | `Settings` from environment variables; range validation ([Configuration keys](interfaces.md#configuration-keys)) | extend |
| `app/schemas.py` | The HTTP and model-output contracts ([API contract](data-models.md#api-contract)) | extend (ADR 0005) |
| `app/logjson.py` | JSON log formatter, `request_id` context variable | given |
| `app/routes/ask.py` | `POST /api/ask`; sets the `X-Cache` header | extend |
| `app/routes/health.py` | `/healthz` (touches nothing); `/readyz` (index state and Redis) | implement |
| `app/routes/metrics.py` | Metric definitions and `/metrics` ([Metrics](observability.md#metrics)) | extend |
| `app/services/answer.py` | Runs the pipeline steps in order. Stays thin: each step lives in its own module | extend |
| `app/services/index_state.py` | Reads the active pointer and collection metadata, checks the embedding pin, tells the cache when the version changes | new |
| `app/services/query_intent.py` | Detects follow-ups (from the question and whether `history` is empty) and explicit requests for an older version; extracts exact terms | new |
| `app/services/prompt.py` | Builds the messages exactly per the [Prompt contract](interfaces.md#prompt-contract); holds `PROMPT_VERSION` | new |
| `app/services/validate.py` | Parse, schema check, semantic and citation checks ([Output validation](validation-and-errors.md#output-validation)) | new |
| `app/services/fallback.py` | The canned abstention and fallback answers | new |
| `app/services/cache.py` | `SemanticCache` on Redis ([Semantic cache](workflows.md#semantic-cache)) | new |
| `app/services/turns.py` | `TurnLog` on Redis: appends every turn to `rahbar:turns` | new |
| `app/retrieval/base.py` | `Retriever` protocol ([Internal interfaces](interfaces.md#internal-interfaces)) | extend (signature) |
| `app/retrieval/stub.py` | Three fixed passages for the first days | given |
| `app/retrieval/chroma.py` | Dense query plus the optional keyword query, superseded filter, distance converted to similarity | implement |
| `app/retrieval/fusion.py` | Reciprocal Rank Fusion ([D9](decisions.md#d9-light-hybrid-retrieval)) | new |
| `app/providers/embedding/base.py` | `Embedder` protocol | new |
| `app/providers/embedding/fastembed.py` | Query embeddings from the model baked into the image ([D7](decisions.md#d7-embeddings-inside-the-images)) | new |
| `app/providers/embedding/dummy.py` | Hash vectors for the `dummy-768` index (STARTER first-days flow) | new |
| `app/providers/llm/base.py` | `LLMProvider` protocol: messages in, raw completion out | extend (signature) |
| `app/providers/llm/hosted.py` | Groq through the OpenAI-compatible API ([Groq contract](interfaces.md#groq-contract)) | implement |
| `app/providers/llm/ollama.py` | Thin Ollama client, not deployed ([D10](decisions.md#d10-thin-ollama-provider)) | implement |
| `app/providers/llm/stub.py` | Deterministic JSON reply; cites the first passage | extend (signature) |

**Start-up and shutdown.**

- **Start-up.** Loading the embedding model takes seconds and must finish well inside the
  startup probe's 60-second budget. The first index-state check is logged, and a pin conflict
  is logged at ERROR.
- **Shutdown.** Follows the timing chain in
  [deployment.md § Rollout settings](deployment.md#rollout-settings).

**Scaling.** The api is stateless; all state lives in Redis and Chroma. The HPA scales it from 3
to 8 replicas. Each pod holds its own copy of the embedding model, roughly 250–400 MB to be
measured.

## Indexer

**Responsibility.** Turn the corpus into a new, complete, activated index, then exit
([Indexing run](workflows.md#indexing-run)). It is the only code that writes to Chroma.

**Must never:**

- touch Redis (§4.7)
- move the pointer before the new collection's count has been verified
- delete the active or the previous collection

| Module | Responsibility | Status |
| --- | --- | --- |
| `pipeline/run.py` | Command line (`--dummy`), document discovery, stage runner, wait for Chroma, exit codes | extend |
| `pipeline/config.py` | `IndexerSettings` from environment variables | extend |
| `pipeline/models.py` | `Page`, `Document`, `Chunk` ([Indexer records](data-models.md#indexer-records)) | extend |
| `pipeline/extract.py` | PDF text and tables (pdfplumber), OCR fallback (pytesseract and pdf2image), HTML, Markdown | implement |
| `pipeline/clean.py` | Normalisation; repeating header and footer removal; headings kept | implement |
| `pipeline/tokens.py` | Token counting with the embedding model's tokenizer ([D14](decisions.md#d14-chunking-approach)) | new |
| `pipeline/chunk.py` | Structure-aware chunker, plus the `fixed` strategy for failure analysis | implement |
| `pipeline/embed.py` | Passage embeddings in batches from the baked model; dummy vectors for `dummy-768` | implement |
| `pipeline/store.py` | Blue/green write, verification, pointer move, pruning ([Active pointer](data-models.md#active-pointer)) | implement |
| `pipeline/dummy.py` | Three-chunk dummy index, written through `store.py`'s blue/green helpers | extend |

**System packages in the image:** `tesseract-ocr`, `tesseract-ocr-eng`, `poppler-utils`.

**Memory.** The indexer is the memory peak of the system, from OCR at 300 dpi and embedding
batches. Its limit is set from `kubectl top pods` measured during a real run
([Resources](deployment.md#resources)). Exceeding it ends the container with exit code 137
(OOMKilled).

## Corpus fetcher

**Responsibility.** Put exactly the committed corpus on the `corpus` PVC
([D5](decisions.md#d5-corpus-delivered-by-an-initcontainer)).

- **What runs.** `corpus/fetch.py` (given), extended with `--out DIR` and `--strict`
  ([Command-line interfaces](interfaces.md#command-line-interfaces)). It runs as the
  initContainer `fetch-corpus`, from the indexer image.
- **Inputs baked into the image.** `corpus/sources.yaml` and `corpus/MANIFEST.md`, the committed
  checksums. Building the image this way is confirmed default
  [P1](decisions.md#proposed-defaults).
- **Politeness rules (§2).** One request at a time, a 2-second pause, a clear User-Agent, each
  file downloaded once, public pages only. Never SLATE, Flex, NU Mail or anything behind a login.
- **Must never** replace the committed `MANIFEST.md`. In the cluster it writes only into the PVC.

## UI

**Responsibility.** Serve `ui/index.html` (given) from nginx on port 8080 as a non-root user with
a read-only root filesystem. `ui/nginx.conf` is given.

| File | Change | Status |
| --- | --- | --- |
| `ui/index.html` | Keep the last 3 turns of the tab in a JavaScript array (answers shortened to 600 characters) and send them as `history` with each question ([D4](decisions.md#d4-conversation-history-and-follow-ups)) | extend |
| `ui/nginx.conf` | None | given |
| `ui/Dockerfile` | `nginxinc/nginx-unprivileged` at a pinned tag, `USER 101`, exec-form `CMD` | new |

The UI already renders model output with `textContent`, never `innerHTML`. Keep it that way
([Untrusted content](security.md#untrusted-content)).

## Chroma

**Responsibility.** Store the indexes and the pointer on a persistent volume. It runs as a
StatefulSet; the reason is given in
[ARCHITECTURE.md](../../ARCHITECTURE.md#why-chroma-is-a-statefulset-not-a-deployment).

- **Image.** `chromadb/chroma:1.0.12`, the same version as the `chromadb-client==1.0.12` Python
  client. If one changes, change the other.
- **Storage and port.** Data in `/data`; port 8000; heartbeat at `GET /api/v2/heartbeat`.
- **Access.** Reached only from the api and the indexer (C4 and C7 in the
  [Connection matrix](system-structure.md#connection-matrix)).

## Redis

**Responsibility.** Hold the semantic cache and the turn log
([Redis keyspace](data-models.md#redis-keyspace)).

- **Persistence.** The append-only file is switched on, on a PVC, as §4.1 asks.
- **Memory.** A memory cap with the `volatile-lru` policy: when the cap is reached, Redis evicts
  the least recently used keys among those with a TTL, and every RAHBAR key has one.
- **Deployment strategy.** `Recreate`, so two Redis processes never open one volume at the same
  time.
- **Access.** Reached only from the api (C5).

## Evaluation runner

**Responsibility.** Score a live stack against a golden set and turn the scores into the CI gate
(§5).

| File | Responsibility | Status |
| --- | --- | --- |
| `eval/run_eval.py` | `recall_at_k`, `citation_validity`, `summarise`, `gate`; plus a `--pause` option to stay inside Groq rate limits | implement |
| `eval/golden.yaml` | The real-corpus golden set ([Golden set](testing-and-evaluation.md#golden-set)) | new |
| `eval/baseline.json`, `eval/results.json` | Real-corpus numbers, committed | new |
| `eval/fixtures/baseline.fixture.json` | Fixture numbers for the CI gate ([D8](decisions.md#d8-stub-llm-in-ci)) | new |
| `eval/cache_pairs.yaml`, `eval/tune_cache.py` | Data and script for choosing the cache threshold ([Tuning procedures](testing-and-evaluation.md#tuning-procedures)) | new |
