# ADR 0003: The semantic cache lives in Redis, keyed by index version

## Status
Accepted · 6 November 2026 (design decision D3)

## Context
Section 3.3 asks for a semantic cache: a new question whose embedding is close enough to an
earlier one gets the earlier answer without retrieval or an LLM call. Each Groq answer costs
about 3,200 tokens out of a daily budget of 200,000, and takes seconds, so repeats are worth
catching. The brief sets four further rules:

1. The cache lives in Redis or in a second Chroma collection.
2. A hit is a cosine similarity at or above a threshold that comes from the ConfigMap and is
   chosen from data: "the lowest threshold with zero false hits on your test questions".
3. Follow-up questions, abstentions, out-of-scope answers and anything that failed validation
   are never cached.
4. Running the indexing Job must expire the cache, because an answer built from the old index
   may now be wrong.

Two of our own decisions constrain the choice. The API never writes to Chroma; only the
indexer Job does (ADR 0001). And the NetworkPolicy allows exactly "redis from api only"
(section 4.7), so the indexer cannot reach Redis.

## Decision
**Redis, with the active index version inside every cache key, and the API cleaning up old
keys itself.**

- **Keys.** `rahbar:cache:<index_version>:<fingerprint>:<mode>:idx` is a sorted set of entry
  ids; `…:e:<id>` is a hash with the unit question vector (384 float32 values), the question,
  and the full `AskResponse` without its `request_id`.
  - `index_version` is the active collection name, for example `rahbar-v20261105-173003`.
  - `fingerprint` is 8 hex characters of a SHA-256 over the settings that change an answer:
    prompt version, model, temperature, `TOP_K`, `RELEVANCE_FLOOR`, `HYBRID_RETRIEVAL` and
    `SUPERSEDED_FILTER`.
  - `mode` is `cur`, or `all` when the user asked about an older document version, so a
    question about the 2023 rules can never hit an answer about the 2026 rules.
- **Lookup.** Read the namespace's entry ids, fetch their vectors in one Redis pipeline, and
  take the best dot product of unit vectors. It is a hit if that is at least
  `CACHE_THRESHOLD`. At most `CACHE_MAX_ENTRIES` (500) vectors are compared, which takes about a
  millisecond in Python.
- **Threshold: 0.96.** We labelled 22 question pairs about our corpus: 11 paraphrases and 11
  near misses, each of which changes one detail that changes the answer
  (`eval/cache_pairs.yaml`). With the pinned `bge-small-en-v1.5` embeddings:

  | Threshold | Paraphrases served | Wrong answers served |
  | --- | --- | --- |
  | 0.88 | 9/11 | 9/11 |
  | 0.92 | 5/11 | 7/11 |
  | 0.95 | 2/11 | 1/11 |
  | **0.96** | 2/11 | **0/11** |

  0.95 was ruled out by one pair: "What is the minimum CGPA required for an **undergraduate**
  degree?" against "…for a **graduate** degree?", at 0.9533. The planned values 0.88 to 0.95
  all served a wrong answer, so we added 0.96, the lowest tested value with none
  (`docs/evidence/cache-threshold.txt`).
- **What is stored.** Only a validated answer on attempt 1 or 2 that is answered from the
  context, keeps at least one citation, and had no citation or inline marker dropped, and only
  when the question is not a follow-up. Abstentions (floor, model or out-of-scope), fallbacks
  and cache hits are never stored (`is_cacheable()` in `services/cache.py`).
- **Expiry on re-index.** When an API pod sees the pointer name a new collection (and once when
  it starts), it compares the version with `rahbar:cache:version`. If they differ, it records
  the new version and `SCAN`s and `UNLINK`s every cache key of any other version. Old answers
  are unreachable from the moment a pod switches namespace, so the deletion is clean-up, and the
  24-hour TTL on every key backs it up.
- **Failure.** Any Redis error during a lookup, store or clean-up is logged at WARNING and
  counted in `rahbar_dependency_errors_total{dependency="redis"}`. The request still gets its
  answer. Readiness, not the cache, takes a pod with a dead Redis out of the Service.

## Options considered
- **A second Chroma collection for the cache.** Chroma would do the nearest-neighbour search
  for us, but the API would become a Chroma writer, which breaks the single-writer rule of
  ADR 0001. The cache would also share Chroma's volume with two full indexes during a re-index.
- **Let the indexer Job flush Redis at the end of a run.** This is the most direct reading of
  "expire on re-index", but it needs a NetworkPolicy exception (indexer → redis) that
  section 4.7 does not list, and a Job that dies after moving the pointer but before flushing
  would leave stale answers live. Versioned keys cannot go stale.
- **Exact-text cache (hash of the question).** Simple and never wrong, but "What is the minimum
  attendance?" and "minimum attendance required?" would both miss. It is not semantic, so it
  does not meet the brief.
- **A vector index inside Redis (RediSearch).** It needs Redis Stack instead of the plain
  pinned `redis:7.4` image, which is a bigger image and a new dependency, for 500 vectors that a
  loop compares in a millisecond.

## Consequences
- **Easier.** A re-index, a rollback of the pointer, or a ConfigMap change to any answer-shaping
  setting each starts a fresh namespace with no manual flush. A cache hit returns the stored
  citations together with the stored `retrieved` list, so citations still match retrieval.
  Redis also holds the turn log (ADR 0005), so one store serves both.
- **Harder.** The threshold that is safe for this small embedding model is high. At 0.96 only
  near-identical rewordings hit (2 of 11 paraphrases), so the cache saves less than it could.
  Lowering it would need a stronger embedding model or an extra check, such as requiring the
  same numbers and clause references in both questions. One-word changes ("undergraduate" vs
  "graduate", "A-minus" vs "B-minus") score 0.94 to 0.95 with this model.
- **What to watch.** `rahbar_cache_hit_ratio` per pod. A ratio near zero in normal use means
  the threshold is too strict for real traffic. Any report of a wrong cached answer means a new
  near-miss pair for `cache_pairs.yaml` and a re-run of `eval/tune_cache.py`. Redis memory: at
  most 500 entries of about 6 KB per namespace, under the 200 MB `volatile-lru` cap.
