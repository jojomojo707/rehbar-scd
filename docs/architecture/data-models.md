# Data models

Every data shape RAHBAR stores or exchanges, defined once. Who reads and writes each one is in
[system-structure.md § Data ownership](system-structure.md#data-ownership).

Changes to the starter's request, response or metadata contracts are marked **new**. They must
be justified in ADR 0005 (STARTER.md: "If you change a contract … say why in an ADR").

## API contract

File: `api/app/schemas.py`. The UI, `eval/run_eval.py` and the tests all depend on these shapes.

```python
class HistoryTurn(BaseModel):      # new: one earlier turn, sent back by the browser
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
    answer: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]

class AskRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
    history: list[HistoryTurn] = Field(default_factory=list, max_length=10)   # new: oldest first

class Passage(BaseModel):          # given: one retrieved chunk, retriever to generator
    chunk_id: str
    text: str
    source: str
    section: str
    page: int | None = None
    score: float                   # cosine similarity = 1 - cosine distance (higher is closer)

class Citation(BaseModel):         # given
    source: str
    section: str
    page: int | None = None

class RetrievedRef(BaseModel):     # given: what the response says was retrieved
    chunk_id: str
    source: str
    section: str
    page: int | None = None
    score: float

class AskResponse(BaseModel):
    request_id: str
    answer: str
    citations: list[Citation]
    answered_from_context: bool
    confidence: Literal["high", "medium", "low"]
    retrieved: list[RetrievedRef]
    provider: str
    cached: bool = False           # new: the UI already shows a cache chip for this field
```

**Rules:**

- `Answer.reasoning` is never copied into `AskResponse` and never logged (R-GEN-07).
- The schema caps (10 turns, 2,000-character answers) only reject abuse with a `422`. The
  working limits are `HISTORY_MAX_TURNS` and `HISTORY_ANSWER_MAX_CHARS`, applied by trimming
  ([Follow-up questions](workflows.md#follow-up-questions)).
- Every `citations` entry matches an entry in `retrieved` ([Matching rules](#matching-rules)).
- `retrieved` is in final rank order. `score` is always the cosine similarity, even when the
  ranking came from fusion.
- A cache hit returns the `retrieved` list stored with the answer, with `cached: true` (AMB-10).

## Model output contract

`Answer` (given, unchanged) is the single definition the model must fill (R-GEN-01):

```python
class Answer(BaseModel):
    reasoning: str                 # short working; stripped before display
    answer: str                    # claim-bearing sentences carry [source / section] markers
    citations: list[Citation]
    answered_from_context: bool
    confidence: Literal["high", "medium", "low"]
```

**Strict schema for Groq.** Groq's `strict: true` mode requires every property to be listed in
`required` and `additionalProperties: false`, and optional values to be written as type unions.
A helper `strict_answer_schema()` in `services/prompt.py` derives this from `Answer`, so the
model contract is never written twice:

```json
{
  "type": "object", "additionalProperties": false,
  "required": ["reasoning", "answer", "citations", "answered_from_context", "confidence"],
  "properties": {
    "reasoning": {"type": "string"},
    "answer": {"type": "string"},
    "citations": {"type": "array", "items": {
      "type": "object", "additionalProperties": false,
      "required": ["source", "section", "page"],
      "properties": {"source": {"type": "string"}, "section": {"type": "string"},
                     "page": {"type": ["integer", "null"]}}}},
    "answered_from_context": {"type": "boolean"},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]}
  }
}
```

**Completion** (internal, `providers/llm/base.py`): what a provider returns before validation.

```python
@dataclass
class Completion:
    text: str            # raw message content: JSON expected, never trusted
    tokens_in: int       # usage.prompt_tokens (0 for the stub)
    tokens_out: int      # usage.completion_tokens (0 for the stub)
    model: str
```

## Indexer records

File: `indexer/pipeline/models.py`. `Page` and `Document` are given; `Chunk` is extended.

| Record | Fields | Notes |
| --- | --- | --- |
| `Page` | `source`, `page` (1-based), `text`, `ocr` | `ocr=True` when the page had no text layer |
| `Document` | `source`, `doc_version`, `superseded`, `pages` | Built by `extract`, rewritten by `clean` |
| `Chunk` | `id`, `text`, `source`, `section`, `page`, `doc_version`, `superseded`, plus **new** `ocr`, `chunk_index`, `tokens` | `metadata()` returns the [Chunk metadata](#chunk-metadata) |

- **Chunk id.** `<source slug>:<chunk_index, 5 digits>`, for example
  `academic-rules-handbook-jun-2026:00042`. It stays the same for the same document and chunking
  settings, and it is unique within a collection.
- **Chunk text.** The section heading on the first line, then the body. Overlap is included, and
  counts toward storage amplification ([D14](decisions.md#d14-chunking-approach)).

## Chunk metadata

Stored per record in Chroma. Values must be `str`, `int`, `float` or `bool`.

| Key | Type | Required by | Meaning |
| --- | --- | --- | --- |
| `source` | str | §3.1 | File name in the corpus directory, for example `academic-rules-handbook-jun-2026.pdf` |
| `section` | str | §3.1 | The heading the chunk sits under, for example `5.4 Academic Warning`. Falls back to the document title when there is no heading. Never empty |
| `page` | int | §3.1 | Page where the chunk starts; `1` for HTML and Markdown (A-03) |
| `doc_version` | str | §3.1 | From `_index.json` or front matter, for example `2026-06` |
| `superseded` | bool | §3.1 | `true` when a newer edition of the same document is in the corpus |
| `ocr` | bool | **new** | The chunk's text came from OCR |
| `chunk_index` | int | **new** | Position within the document |
| `tokens` | int | **new** | Token count of the stored text |

## Collection metadata

One index version is one Chroma collection. Its metadata carries the pin (§4.4) and the build
facts:

| Key | Type | Meaning |
| --- | --- | --- |
| `hnsw:space` | str | Always `cosine` |
| `embed_model` | str | **The pin, part 1:** the `EMBED_MODEL` the indexer used |
| `dimension` | int | **The pin, part 2:** vector length (384 for `BAAI/bge-small-en-v1.5`). The key name matches the starter's `dummy.py` (AMB-02) |
| `index_version` | str | The collection's own name; also the cache namespace ([D3](decisions.md#d3-redis-cache-with-versioned-keys)) |
| `status` | str | `building` until verified, then `complete` |
| `created_at` | str | ISO 8601 UTC time |
| `chunk_count`, `document_count`, `skipped_documents` | int | Build facts |
| `chunk_size`, `chunk_overlap` | int | Configuration used |
| `chunk_strategy` | str | `structure` or `fixed` |
| `original_tokens`, `stored_tokens` | int | For storage amplification: stored tokens ÷ original tokens |
| `superseded_versions` | str | Comma-separated `doc_version` values of superseded documents. Used to detect requests for an older version |
| `corpus_digest` | str | SHA-256 over the sorted file checksums |
| `indexer_image` | str | Image tag from the `IMAGE_TAG` environment variable, if set |

## Active pointer

- **Index collections** are named `<CHROMA_COLLECTION>-v<YYYYMMDD>-<HHMMSS>` in UTC, for example
  `rahbar-v20261105-030000`. `CHROMA_COLLECTION` is now a **name prefix** (AMB-18).
- **The pointer** is an empty collection named `<CHROMA_COLLECTION>-active`. Its metadata holds:

| Key | Meaning |
| --- | --- |
| `active` | Name of the collection the API must read |
| `previous` | The collection that was active before; kept as a safety copy (no rollback command is built) |
| `activated_at` | ISO 8601 UTC time of the last move |

**Pruning.** After a successful activation, the indexer deletes every `<prefix>-v*` collection
except `active` and `previous`. A collection still marked `building` is deleted only if it is
older than 6 hours, so a run that is still in progress is never removed. The pointer collection
itself is never deleted.

## Redis keyspace

Every key has a TTL, so every key is eligible for eviction under `volatile-lru`
([Redis](components.md#redis)).

| Key pattern | Type | Contents | TTL |
| --- | --- | --- | --- |
| `rahbar:cache:<index_version>:<fingerprint>:<mode>:idx` | sorted set | Entry ids, scored by creation time. Trimmed to `CACHE_MAX_ENTRIES` | `CACHE_TTL_SECONDS` |
| `rahbar:cache:<index_version>:<fingerprint>:<mode>:e:<entry_id>` | hash | `v`: question vector as float32 bytes; `q`: question text; `resp`: AskResponse JSON without `request_id`; `ts` | `CACHE_TTL_SECONDS` |
| `rahbar:cache:version` | string | The last index version this cache served | none (one key) |
| `rahbar:turns` | list | The turn log: JSON turns `{request_id, ts, question, answer, answered_from_context, outcome, follow_up, history_turns}`; last `TURN_LOG_MAX_ENTRIES` kept. Never read back into a prompt | `TURN_LOG_TTL_SECONDS`, renewed on each append |

**Namespace parts:**

- `fingerprint` is the first 8 hex characters of a SHA-256 over `PROMPT_VERSION`, `LLM_MODEL`,
  `TEMPERATURE`, `TOP_K`, `RELEVANCE_FLOOR`, `HYBRID_RETRIEVAL` and `SUPERSEDED_FILTER`.
  Changing any of these settings starts a fresh namespace.
- `mode` is `cur` (current versions only) or `all` (the user asked about an older version). A
  question about the 2023 rules can therefore never hit an answer about the 2026 rules.

## Corpus files

| File | Committed | Fields |
| --- | --- | --- |
| `corpus/sources.yaml` | yes | Per document: `name`, `url`, `doc_version`, `superseded`, `notes` (format of `sources.example.yaml`) |
| `corpus/MANIFEST.md` | yes | Table of document, version, superseded, file, bytes, SHA-256, URL (written by `fetch.py`) |
| `corpus/raw/_index.json`, or `/corpus/_index.json` in the cluster | no | Per file: `name`, `url`, `file`, `bytes`, `sha256`, `content_type`, `fetched_at`, `doc_version`, `superseded`. The indexer reads this |
| `eval/fixtures/*.md` | yes | Front matter `source`, `doc_version`, `superseded` (given) |

## Evaluation files

**`eval/golden.yaml`.** Same format as the given `eval/fixtures/golden.fixture.yaml`:

```yaml
questions:
  - id: q01                       # unique
    type: ordinary                # ordinary | version | exact | abstain | injection
    question: What CGPA does an undergraduate need to stay off academic warning?
    relevant:                     # (source, section) pairs; empty for abstain questions
      - {source: academic-rules-handbook-jun-2026.pdf, section: "5.4"}
    expect: "2.00"                # optional substring, for human review
    must_abstain: false           # true only for abstain questions
```

**`results.json` and `baseline.json`.** Both are written by `summarise()` plus `main()` in
`run_eval.py`; the gate reads the top-level keys.

```json
{
  "recall@3": 0.81, "recall@5": 0.88,
  "citation_validity": 1.0, "abstention_correctness": 1.0,
  "by_type": {"ordinary": {"n": 8, "recall@3": 0.9, "recall@5": 0.95}, "exact": {"n": 3, "recall@3": 0.5, "recall@5": 0.66}},
  "cache_hits": 0, "fallbacks": 0,
  "rows": [{"id": "q01", "type": "ordinary", "recall@3": 1.0, "recall@5": 1.0, "top_score": 0.83,
            "citation_validity": 1.0, "answered_from_context": true, "cached": false, "seconds": 2.1}],
  "golden": "eval/golden.yaml", "questions": 18
}
```

The numbers above only illustrate the shape.

## Matching rules

These rules are used in two places: the API's citation check (`services/validate.py`) and
`run_eval.py` (recall and citation validity). Both implementations must follow this definition,
and their tests use the examples below.

**Normalise a string.** Apply Unicode NFKC, case-fold, collapse whitespace, and strip trailing
`.` `:` and spaces.

| Comparison | Rule |
| --- | --- |
| Source | Normalised strings are equal |
| Golden section against chunk section (recall) | Equal, **or** the chunk section starts with the golden section followed by a space, `.` or `)` |
| Citation against retrieved passage (citation validity) | Source equal **and** section equal, **and** (`page` is null **or** equals that passage's page) |
| Inline marker `[source / section]` | Split on the first `" / "`, then compare like a citation without a page |

| Golden | Chunk section | Match? |
| --- | --- | --- |
| `5.4` | `5.4 Academic Warning` | yes |
| `5.4` | `5.4.1 Removal from warning` | yes (subsection) |
| `5.4` | `5.41 Fees` | no |
| `2. Academic warning` | `2. Academic warning` | yes |

**Aggregates:**

- **recall@k for one question** = matched golden pairs ÷ all golden pairs. It is `None` when the
  question has no golden pairs (abstain questions).
- **Overall and per-type recall** = the mean over the questions that are not `None`.
- **Citation validity** = valid citations ÷ all citations across the run. It is `None` when no
  answer carried a citation.
