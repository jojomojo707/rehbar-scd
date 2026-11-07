# Validation and error handling

The rules that decide whether a request, a configuration, a retrieval or a model reply is
accepted, and what happens when one is not. The order these rules run in is in
[workflows.md § Query pipeline](workflows.md#query-pipeline).

## Input validation

| Input | Rule | On failure |
| --- | --- | --- |
| `question` | Leading and trailing whitespace stripped, then 3–500 characters (R-QRY-01). Control characters other than newline and tab removed | `422` |
| `history` | Optional list, at most 10 turns; each `question` 3–500 characters, each `answer` at most 2,000. Then trimmed to the newest `HISTORY_MAX_TURNS` turns, answers cut to `HISTORY_ANSWER_MAX_CHARS` | `422` beyond the caps; trimming never fails |
| Unknown JSON fields | Ignored | (none) |
| `X-Request-ID` | Matches `^[A-Za-z0-9._-]{1,64}$` | A new id is generated (this also prevents log injection) |

## Configuration validation

Checked once at start-up in `config.py` (api) and `pipeline/config.py` (indexer).

| Condition | Result |
| --- | --- |
| A key is not a number where one is expected; `TOP_K` outside 1–20; `RELEVANCE_FLOOR` or `CACHE_THRESHOLD` outside 0–1; `TEMPERATURE` outside 0–2; `CHUNK_OVERLAP ≥ CHUNK_SIZE`; `CHUNK_SIZE > 512` | The process exits with an ERROR log naming the key. The pod shows `CrashLoopBackOff`, which makes a bad ConfigMap visible at once |
| Unknown `RETRIEVER` or `LLM_PROVIDER` | Same (the given factories already raise) |
| `TEMPERATURE > 0.3` | WARNING log: "outside the factual range of §3.4". Allowed, so stage F can be shown |
| `LLM_PROVIDER=hosted` and `LLM_API_KEY` empty | ERROR log at start-up. The pod still becomes ready; every answer falls back with reason `provider_not_configured` |
| `EMBED_MODEL` not present in the image | Not a crash: the `embedding_model` readiness check fails (pod `0/1 READY`) |

## Relevance floor and abstention

- **Floor abstention.** After retrieval, take the best cosine similarity among the returned
  passages. If no passages came back, or the best is below `RELEVANCE_FLOOR`, the API **abstains
  without calling the LLM** (R-GEN-03). The metric reason is `relevance_floor`.
- **Model abstention.** If the model replies `answered_from_context: false`, the reply is
  accepted as an abstention, and its citations are cleared. The metric reason is `model`.
- **What the user receives** in both cases:
  - `answer`: *"The documents I have do not cover this question, so I can't answer it from them."*
  - `citations: []`, `answered_from_context: false`, `confidence: "low"`
  - `retrieved`: what was retrieved, kept for transparency and evaluation
- **Choosing the floor value:** see
  [testing-and-evaluation.md § Tuning procedures](testing-and-evaluation.md#tuning-procedures).

## Output validation

Every model reply goes through these steps, in order. The first failure ends validation for that
attempt and is recorded as the reason.

| # | Check | Failure reason |
| --- | --- | --- |
| 1 | `json.loads` succeeds | `invalid_json` |
| 2 | `Answer.model_validate` succeeds | `schema` |
| 3 | `answer` is non-empty and at most 4,000 characters | `schema` |
| 4 | If `answered_from_context` is false, the reply is treated as an abstention (above). Validation ends here, successfully | (none) |
| 5 | Citations not matching a retrieved passage are **dropped** and counted ([Citation rules](#citation-rules)) | (none, but recorded) |
| 6 | Inline `[source / section]` markers not matching a retrieved passage are removed from `answer` and counted | (none, but recorded) |
| 7 | At least one valid citation remains | `no_valid_citation` |
| 8 | Every sentence without a valid inline marker gets one **only if exactly one source was validated** (then the attribution is certain). With two or more sources, at least one valid inline marker must already remain in `answer` | `no_inline_citation` |

**Never used:** model output is never passed to `eval`, `exec`, a shell, or SQL (R-SEC-05), and
`reasoning` is discarded after validation.

## Citation rules

- **Matching.** A citation is valid only if it matches a passage retrieved **for this request**,
  using the rules in [data-models.md § Matching rules](data-models.md#matching-rules) (R-GEN-04).
  The API guarantees this by dropping invalid citations before responding, so a returned
  citation can never be fabricated (the −10 deduction).
- **Cache hits.** A hit returns the citations and the `retrieved` list stored together, so they
  still match each other (AMB-10).
- **No partial caching.** An answer that had any citation dropped is **not cacheable**, because a
  model that invented one source may have invented a claim.

## Retry and fallback

Each request gets **at most two generation attempts** (R-GEN-02, R-QRY-07).

| Attempt result | Next step |
| --- | --- |
| Valid | Respond |
| `invalid_json`, `schema`, `no_valid_citation`, `no_inline_citation`, provider `bad_request` | Retry once, with the correction turn ([Prompt contract](interfaces.md#prompt-contract)) |
| Provider `timeout`, `server` | Retry once after a 1-second pause, with no correction turn |
| Provider `rate_limited` | Retry once after the wait the provider asked for (`Retry-After`, or Groq's "try again in Xs"), at most 10 s (`RATE_LIMIT_MAX_WAIT_SECONDS` in `answer.py`), with no correction turn. Groq's free tier allows 8,000 tokens a minute, about five questions |
| Provider `auth`, `not_configured` | Fall back at once; retrying cannot help |
| Second attempt fails for any reason | Fall back |

**The canned fallback.**

- `answer`: *"I couldn't produce a reliable, cited answer right now. Please try again in a
  moment."*
- `citations: []`, `answered_from_context: false`, `confidence: "low"`, `retrieved` kept.
- Never cached. Counted as `rahbar_fallbacks_total{reason=…}`.

**Worst-case latency** is about 2 × `LLM_TIMEOUT_SECONDS` plus 1 second, roughly 41 seconds. The
Ingress timeout and the shutdown grace period are sized from this
([Rollout settings](deployment.md#rollout-settings)).

## Cacheability

An answer is stored in the cache only if **all** of these hold (R-CAC-04):

1. The question is not a follow-up.
2. It is a validated answer on attempt 1 or 2: not an abstention, not a fallback, not itself a
   cache hit.
3. `answered_from_context` is true and at least one valid citation remains.
4. No citation or inline marker was dropped.
5. Redis is reachable.

So follow-ups, abstentions (including the out-of-scope ones, A-07), fallbacks and anything that
failed validation are never cached.

## Error mapping

`/api/ask` returns **only 200 or 422** (AMB-11). Failures show up in the response fields, metrics
and logs, never as a 5xx.

| Condition | HTTP | Response | Metric | Log |
| --- | --- | --- | --- | --- |
| Invalid request body | 422 | FastAPI detail | `rahbar_requests_total{status="422"}` | INFO |
| Abstention | 200 | Canned abstention | `rahbar_abstentions_total{reason}` | INFO |
| Fallback | 200 | Canned fallback | `rahbar_fallbacks_total{reason}` | WARNING |
| Redis error during cache or turn-log handling | 200 | Normal answer; cache and turn log skipped | `rahbar_dependency_errors_total{dependency="redis"}` | WARNING |
| Chroma error during retrieval | 200 | Fallback, reason `retrieval_error` | `…{dependency="chroma"}` | ERROR |
| Embedding error | 200 | Fallback, reason `embedding_error` | `rahbar_fallbacks_total` | ERROR |
| Any other exception in the pipeline | 200 | Fallback, reason `internal_error` | `rahbar_fallbacks_total` | ERROR, with stack trace |
| Pod not ready | (no traffic) | Withheld from the Service by `/readyz` returning `503` | (none) | WARNING on each state change |
| Rate limit at the Ingress (optional hardening) | 429 | nginx | (none) | (none) |

## Degraded modes

| Dependency down | Requests already reaching the pod | Readiness |
| --- | --- | --- |
| Groq | Fallback answers; floor abstentions still correct | Unaffected: the LLM is not a readiness dependency (§4.3) |
| Redis | Answers without the cache or the turn log | Fails within about 30 s (3 × 10 s), and the pod is withheld |
| Chroma | Fallback answers | Fails, and the pod is withheld |
| Pointer moved to a mismatched index | (none) | Fails on `embedding_pin` |

## Indexer failures

| Failure | Behaviour | Exit | What the operator sees |
| --- | --- | --- | --- |
| A download fails | initContainer exits; the pod restarts it up to `backoffLimit` | 1 | `kubectl logs <pod> -c fetch-corpus` names the URL |
| A checksum differs from MANIFEST.md | initContainer exits. A retry cannot help: the website changed the file | 1 | The log line `changed <file>`. Update the manifest deliberately through a PR |
| Chroma unreachable after `CHROMA_WAIT_SECONDS` | Exits | 1 | `chroma unreachable` log line |
| One document fails to extract, or yields no text | **Skipped** ("survives a bad document"); counted in `skipped_documents` | (none) | ERROR log with the file and the cause |
| No chunks at all | Exits before creating a collection | 1 | `no chunks produced` |
| A chunk is missing a required metadata field | Exits before activation | 1 | ERROR naming the chunk id |
| A vector's dimension differs from the model's | Exits before activation | 1 | ERROR with both dimensions |
| Count after writing differs from chunks produced | Collection left as `building`, pointer untouched | 1 | ERROR with both counts |
| Memory limit exceeded | Container killed; restarted up to `backoffLimit` | 137 | `kubectl describe pod`: `OOMKilled` |
| A stage is not implemented yet | Given behaviour | 2 | `indexer stage not implemented yet` |
