# Design decisions

Every design choice that is not dictated word for word by the brief (`SCD_A02.md`) is recorded
here once, with the options weighed and the consequences. Other architecture files link here
instead of repeating the reasoning.

The ADRs in [`docs/adr/`](../adr/) are **written by the team in their own words** (brief §4.2,
§8). This file is their reference material, not a substitute. Which ADR covers which decision is
listed in [ARCHITECTURE.md](../../ARCHITECTURE.md#adrs-the-team-writes).

## Decision index

| ID | Decision | Choice | Status | ADR |
| --- | --- | --- | --- | --- |
| D1 | Where indexing runs | A Kubernetes Job; the API only reads | Mandated (§4.2) | 0001 |
| D2 | How a re-index replaces the live index | Blue/green collections plus an active pointer | Confirmed | 0001 |
| D3 | Cache store and invalidation | Redis; index version inside every key; API-side invalidation | Confirmed | 0003 |
| D4 | Follow-up questions and turns | Optional `history` (last 3 turns) sent by the browser; every turn logged to Redis | Confirmed | 0005 |
| D5 | How documents reach the indexer | initContainer fetch and checksum check into a corpus PVC | Confirmed | (PIPELINE.md) |
| D6 | LLM provider | Groq through the `hosted` mode, `openai/gpt-oss-20b`, strict structured outputs | Confirmed | 0004 |
| D7 | Embedding source | fastembed with `BAAI/bge-small-en-v1.5`, baked into the api and indexer images | Confirmed | 0004 |
| D8 | Models in CI | Real embeddings, stub LLM, separate fixture baseline, `ci` overlay | Confirmed | (none) |
| D9 | Exact-term retrieval | Light hybrid: Chroma `$contains` leg plus Reciprocal Rank Fusion, behind a switch | Confirmed | 0002 |
| D10 | `ollama.py` | Thin real implementation, unit-tested, not deployed | Confirmed | (none) |
| D11 | Architecture documentation layout | Root `ARCHITECTURE.md` index plus `docs/architecture/` | Confirmed | (none) |
| D12 | Who writes the ADRs | The team, in their own words | Confirmed | (none) |
| D13 | Corpus | Starter FAST-NUCES list, hostel rules absent, backup version pair | Confirmed | (CORPUS.md) |
| D14 | Chunking approach | Structure-aware, token-sized with the embedding tokenizer, three measured configs | Mandated (§3.1) | 0002 |
| P1–P8 | Smaller defaults | See [Defaults](#proposed-defaults) | Confirmed 2026-11-04 (P4: no redaction) | (none) |

## D1 Indexer runs as a Job

- **Context.** With three API replicas, indexing at start-up means three writers racing on one
  Chroma volume, a full re-index on every restart, dishonest readiness, and no way to re-index
  without a redeploy (§4.2).
- **Choice.** A `Job` named `indexer` and a weekly `CronJob` named `reindex` run the same image and
  arguments. The API never writes to Chroma. The deduction for indexing at API start-up is −10.
- **Detailed in.** [workflows.md § Indexing run](workflows.md#indexing-run),
  [deployment.md § Workload specifications](deployment.md#workload-specifications).

## D2 Blue-green re-index

- **Context.** Re-indexing must cause no downtime and need no redeploy (§4.2). The starter's
  `store.py` asks what happens to the old index while the API serves from it.
- **Options.**
  - (A) Write a new collection per run, then move a pointer.
  - (B) Upsert into one collection and prune. The API sees a half-old, half-new index mid-run,
    and changing the model breaks it with a dimension clash.
  - (C) Delete and recreate. The collection is empty during the run, every API pod fails
    readiness at once, and the service is down.
- **Choice: A.** Each run writes `rahbar-v<UTC timestamp>` with `status: building`. It marks the
  collection `complete` only after the count is verified, then updates the pointer collection
  `rahbar-active`. It keeps the active and the previous collection. Moving the pointer back would
  be a rollback, but no command for it is built: the brief does not ask for one.
- **Consequences.**
  - A crashed run never becomes visible.
  - Two runs cannot corrupt each other.
  - The collection name doubles as the **index version** that D3 uses.
  - Disk briefly holds two indexes.
  - `CHROMA_COLLECTION` becomes a name prefix rather than a single collection name.
- **Detailed in.** [data-models.md § Active pointer](data-models.md#active-pointer),
  [workflows.md § Re-index and rollback](workflows.md#re-index-and-rollback).

## D3 Redis cache with versioned keys

- **Context.** §3.3 asks for the cache to be expired when the indexing Job runs. §4.7 allows
  "redis from api only", so the Job cannot reach Redis. A second Chroma collection would make the
  API a Chroma writer, which breaks D1.
- **Options.**
  - (A) Put the active index version into every cache key, and let the API delete old-version
    keys when it notices a new version.
  - (B) Add a NetworkPolicy exception so the indexer can flush Redis.
- **Choice: A, on Redis.** Redis is also required by §4.1 as a Deployment with a PVC, and it
  stores the turn log (D4).
- **Consequences.**
  - The NetworkPolicy stays exactly as §4.7 lists it.
  - A stale answer cannot be served, because the lookup can no longer match it.
  - The key also carries a configuration fingerprint and a retrieval mode, so changing a
    ConfigMap value, or asking about an older version, never returns a mismatched answer.
- **Detailed in.** [workflows.md § Semantic cache](workflows.md#semantic-cache),
  [data-models.md § Redis keyspace](data-models.md#redis-keyspace).

## D4 Conversation history and follow-ups

- **Context.** §3.2 says "skip [the cache] for follow-up questions" and "store the turn". The
  starter contract carries no conversation identity.
- **Options.**
  - (A) An optional `conversation_id`; the API keeps each conversation's turns in Redis.
  - (B) No conversation data at all; guess follow-ups from the text alone. A follow-up such as
    "what about lab courses?" is then searched on its own and gets a weak answer.
  - (C) The browser sends the last few turns with each question (a context window); the API
    keeps no conversation state.
- **Choice: C.**
  - The request accepts an optional `history`: the last `HISTORY_MAX_TURNS` (3) turns, oldest
    first, each a question and the answer shortened to `HISTORY_ANSWER_MAX_CHARS` (600).
  - A question is a follow-up when `history` is not empty **and** the question refers back to
    it. Only follow-ups use the history; every other question ignores it, so it stays cacheable.
  - Follow-ups are retrieved with the previous question added and are never cached.
  - Every turn is appended to a capped turn log in Redis (`rahbar:turns`), which is what
    "store the turn" means here. The log is for audit; it is never read back into a prompt.
- **Why these sizes.** Groq's limits for `openai/gpt-oss-20b` were 8,000 tokens per minute and
  200,000 per day on the rate-limits page (checked 2026-11-04; confirm on the team's account).
  One request is about 3,200 tokens without history (instructions ~500, five chunks ~2,000,
  question ~100, output ~600). Three turns at these limits add at most about 3,300 characters,
  roughly 800 tokens, keeping a follow-up near 4,000 tokens.
- **Consequences.**
  - This changes the contract: an ADR is required (STARTER.md, "If you change a contract"), and
    `ui/index.html` needs a small edit.
  - `eval/run_eval.py` and `curl` send no history, so they keep working unchanged and never
    produce follow-ups.
  - The history comes from the client, so it is untrusted: it is delimited in the prompt as
    context, never evidence, and citations are still checked only against this request's
    retrieval ([security.md § Untrusted content](security.md#untrusted-content)).
- **Detailed in.** [workflows.md § Follow-up questions](workflows.md#follow-up-questions),
  [data-models.md § API contract](data-models.md#api-contract).

## D5 Corpus delivered by an initContainer

- **Context.** FAST-NUCES files must never be committed (§2). Images are pushed to public Docker
  Hub (§6). A stranger must succeed from a clean clone (§1.3).
- **Options.**
  - (A) An initContainer runs `corpus/fetch.py` into a PVC and checks the checksums.
  - (B) Bake the files into the image. This redistributes the PDFs on Docker Hub.
  - (C) Load a volume by hand. This adds a manual step that breaks the clean-clone requirement.
- **Choice: A.**
  - Files already on the PVC are reused, so the website is rarely contacted again.
  - The checksum check turns a silently changed document into a loud Job failure.
  - The CI fixtures are baked into the image, so CI never contacts nu.edu.pk.
- **Consequences.** The indexer needs internet egress on ports 80 and 443
  ([security.md § Network policy](security.md#network-policy)). The image also needs files from
  outside `indexer/` (proposed default P1).
- **Report.** The team explains this choice in `docs/PIPELINE.md`, as STARTER.md requires.

## D6 Groq for generation

- **Context.** §3.5 requires one provider mode supported fully, behind an interface. The team
  chose not to run Ollama anywhere.
- **Choice.**
  - Use the `hosted` mode against Groq's OpenAI-compatible API, with
    `LLM_MODEL=openai/gpt-oss-20b`.
  - Use Structured Outputs with `strict: true`, the strongest enforcement Groq offers, which §3.4
    asks for. It is available on `openai/gpt-oss-20b`, `openai/gpt-oss-120b` and a few others
    according to Groq's docs (checked 2026-11-04).
  - `openai/gpt-oss-120b` is the fallback model if answer quality is poor.
  - `LLM_REASONING_EFFORT=low`: these models reason before answering, and those tokens count
    against the rate limit (D4 sizes the token budget).
- **Consequences.**
  - The Secret becomes mandatory outside CI.
  - The api needs egress to the internet on port 443.
  - Questions leave the cluster, which ADR 0004 must govern
    ([security.md § Data governance](security.md#data-governance)).
  - Free-tier rate limits apply. Verify them on the team's Groq account.

## D7 Embeddings inside the images

- **Context.** Groq offers no embedding models. Indexer and API must use the identical model
  (§3.2, §4.4).
- **Options.**
  - (A) fastembed, which runs ONNX models on CPU, with `BAAI/bge-small-en-v1.5` (384 dimensions)
    baked into both images at build time.
  - (B) A second hosted vendor. This means a second key, rate limits during indexing, and
    questions sent to two third parties.
  - (C) A shared in-cluster embedding server. This is an extra component to build and operate.
- **Choice: A.**
  - No key and no runtime download.
  - Identical behaviour on minikube, in CI and in CD.
  - Questions are embedded without leaving the cluster.
- **Consequences.**
  - Each api pod needs a few hundred MB more memory, to be measured with `kubectl top pods`.
  - Images grow by about 150 MB.
  - The model's 512-token input limit caps chunk size (D14).
- **Detailed in.** [workflows.md § Startup and readiness](workflows.md#startup-and-readiness).

## D8 Stub LLM in CI

- **Context.** `e2e-eval` (ci.yml) and `deploy` (cd.yml) run on GitHub-hosted runners. The gate
  must fail only when the code gets worse.
- **Choice.**
  - Use real embeddings (D7) with the stub LLM, so recall@5 and abstention are real and
    deterministic.
  - Add a `k8s/overlays/ci` overlay on top of `prod` that changes only configuration. This is an
    addition to the `dev` and `prod` overlays listed in §10.
  - Give the fixture golden set its own baseline: `eval/fixtures/baseline.fixture.json`.
- **Consequences.** In CI, citation validity is trivially 100%, because the stub cites what it was
  given. Real citation validity comes from the Groq runs on minikube, which produce the committed
  `eval/results.json` and `eval/baseline.json`. `PIPELINE.md` must say so.
- **Detailed in.** [testing-and-evaluation.md § Baselines and the CI gate](testing-and-evaluation.md#baselines-and-the-ci-gate).

## D9 Light hybrid retrieval

- **Context.** Embeddings blur exact terms (§2 property 7, §5.2, Engineering Note Q5).
- **Choice.**
  - When the question contains exact terms (clause numbers, course codes, amounts, CGPA
    values), run a second Chroma query restricted with `where_document $contains`.
  - Merge both lists with Reciprocal Rank Fusion.
  - The `HYBRID_RETRIEVAL` switch allows measuring dense-only against hybrid, by question type.
- **Consequences.**
  - The API stays read-only and no new store is needed.
  - `$contains` is a plain substring match (`1.2` also matches `1.21`). Fusion softens this.
- **Detailed in.** [workflows.md § Query pipeline](workflows.md#query-pipeline).

## D10 Thin Ollama provider

- **Context.** §10's layout lists `app/providers/llm/{base,ollama,hosted,stub}.py`. The checker
  fails on any remaining `raise NotImplementedError`.
- **Choice.** About 40 lines that share the prompt contract and call `POST /api/chat` with
  `format=<schema>`, covered by one test against a mocked HTTP transport. It is documented as
  "implemented, not deployed".
- **Consequence.** It also shows §3.5's "a swap is one file".

## D11 Documentation layout

- **Context.** The team asked for `ARCHITECTURE.md` to be a routing index. §4.1 requires the reason
  Chroma is a StatefulSet to appear **in** `ARCHITECTURE.md`.
- **Choice.** The root `ARCHITECTURE.md` is an index plus that one required section. The content
  lives in `docs/architecture/`.
- **Boundary.** Architecture files hold the design. The graded reports (`CORPUS.md`, `PIPELINE.md`,
  `FAILURE-ANALYSIS.md`, `ENGINEERING-NOTES.md`) hold measured results and are written later.

## D12 ADRs are written by the team

- **Context.** §4.2 asks for ADR 0001 in the team's own words. §8 treats undisclosed AI work as
  plagiarism.
- **Choice.** No ADR is drafted by AI. The team writes them from this file, and discloses in
  `docs/AI-USAGE.md` that these architecture files were AI-assisted.

## D13 Corpus selection

- **Choice.**
  - Use the documents in `corpus/sources.example.yaml`.
  - The deliberately absent topic is **hostel rules**: the prospectus's "Transport and Hostel
    Facilities" PDF is left out.
- **Version pairs.**
  - Primary: Undergraduate Academic Rules Aug 2023 (`superseded: true`) against Academic Rules
    Handbook Jun 2026 (`superseded: false`).
  - Backup, if the 2023 PDF does not download: Electrical Engineering learning outcomes, before
    2024 (12 PLOs) against 2024 onwards (11 PLOs), from the IQAE Downloads page.
- **Annual reports.** Annual Report 2019-20 is `superseded: true` and 2023-24 is
  `superseded: false`. An unqualified question answers from the newest report; a question that
  names 2019-20 still reaches the older one (see
  [workflows.md § Query pipeline](workflows.md#query-pipeline)).
- **Open risks.**
  - The 2023 PDF "would not open when checked" (§2).
  - The scanned ORIC policy must be confirmed with `pdffonts`.
  - The corpus must be named in the first pull request (§2).

## D14 Chunking approach

- **Mandated.** Split structure-aware (sections, then paragraphs, then sentences) with overlap,
  and measure at least three configurations with recall@5 (§3.1).
- **Choices.**
  - **Unit.** Tokens, counted with the embedding model's own tokenizer, so a chunk never exceeds
    the model's 512-token limit. Truncation would silently drop text.
  - **Candidate configurations.** (256, 32), (384, 48), (480, 64), all within the limit. The
    shipped value comes from the measured recall@5.
  - **Chunk text format.** Each chunk's text starts with its section heading. This helps
    retrieval and counts toward storage amplification.
  - **Sections.** Overlap never crosses a section boundary, so every chunk belongs to exactly one
    citable section.
  - **Tables.** Kept whole where they fit; otherwise split by rows, with the header row repeated.
- **Detailed in.** [workflows.md § Indexing run](workflows.md#indexing-run),
  [testing-and-evaluation.md § Tuning procedures](testing-and-evaluation.md#tuning-procedures).

## Proposed defaults

These are smaller choices taken as defaults so the design is complete. Each can be changed
without affecting the decisions above. **Confirmed by the team on 2026-11-04.** P4 was changed
from the proposal: the brief does not ask for redaction, so none is built.

| ID | Default | Why | Alternative |
| --- | --- | --- | --- |
| P1 | Build the indexer image with named build contexts: `docker build --build-context corpus=corpus --build-context fixtures=eval/fixtures indexer` | The image needs `corpus/fetch.py`, `sources.yaml`, `MANIFEST.md` and the fixtures. These sit outside `indexer/`, and this keeps `indexer/.dockerignore` meaningful. Needs Docker 23 or later with buildx. | Build from the repository root with `-f indexer/Dockerfile` |
| P2 | `LICENSE` is MIT | The layout in §10 requires a LICENSE file | Any OSI licence |
| P3 | Logs carry a question hash and length, never the raw question text | Personal data could otherwise end up in logs | Log the question text |
| P4 | **No PII redaction.** Question text goes to Groq, the cache and the turn log unchanged; ADR 0004 records this as an accepted risk | The brief (§3–§8) never asks for redaction; the only related requirement is ADR 0004 on data governance. The team chose not to build what is not required | (rejected) Regex masking of emails, phone numbers, roll numbers and CNICs before Groq and the cache |
| P5 | Failure-injection switches in the ConfigMap: `OCR_ENABLED`, `CHUNK_STRATEGY`, `SUPERSEDED_FILTER` | Stages A, B and E of §5.5 can then be broken and restored without code edits | Break the stages on code branches |
| P6 | Starting numbers: `TOP_K=5`, `TEMPERATURE=0.2`, `LLM_TIMEOUT_SECONDS=20`, cache thresholds tried 0.88/0.92/0.95, the shutdown timing chain in [deployment.md § Rollout settings](deployment.md#rollout-settings) | Reasonable starting points that measurement replaces | (none) |
| P7 | `reindex` runs Sundays 03:00, `timeZone: Asia/Karachi` | Low-traffic hour | Any weekly slot |
| P8 | cd.yml's `deploy` uses the `ci` overlay (stub LLM), pulling the SHA-tagged images from Docker Hub | Deterministic smoke test; no Groq key in GitHub | Groq key stored in GitHub Secrets for a real smoke answer |
