# Observability

What RAHBAR logs and measures, and how those signals are used to find which stage broke (§4.8,
§5.5, §9).

## Logs

- **Format.** One JSON object per line, written to **stdout only**, never to a file (R-OBS-01).
  The api uses the given `app/logjson.py`; the indexer uses the given `log()` in
  `pipeline/run.py`.
- **Fields on every api line.** `ts`, `level`, `logger`, `msg`, `request_id`, plus the
  structured `extra=` fields.
- **`request_id`.** Taken from `X-Request-ID` when it is safe
  ([HTTP endpoints](interfaces.md#http-endpoints)), otherwise generated. It is set once per
  request in the middleware and appears on every line of that request (R-OBS-02).
- **Never logged:**
  - `LLM_API_KEY` and `Authorization` headers
  - the model's `reasoning`
  - full retrieved text
  - the raw question: log `question_sha256` (first 12 hex characters) and `question_chars`
    instead (default P3)

| Event | Level | Logger | Key fields |
| --- | --- | --- | --- |
| `api started` | INFO | `rahbar.api` | retriever, llm_provider, embed_model, top_k (given) |
| `embedding pin mismatch` | ERROR | `rahbar.index` | configured_model, index_model, configured_dimension, index_dimension, collection |
| `index version changed` | INFO | `rahbar.index` | old, new, cache_keys_removed |
| `readiness changed` | WARNING | `rahbar.health` | ready, failed, detail |
| `answered` | INFO | `rahbar.answer` | [Request log line](#request-log-line) |
| `request` | INFO | `rahbar.api` | path, status, ms (given) |
| `generation attempt failed` | WARNING | `rahbar.answer` | attempt, reason |
| `dependency error` | WARNING or ERROR | `rahbar.answer` | dependency, error |
| `indexer starting`, `chunked`, `document skipped`, `indexer finished` | INFO or ERROR | `rahbar.indexer` | See [Indexing run](workflows.md#indexing-run) |

## Request log line

Exactly one `answered` line per `/api/ask` request. It extends the given line in
`services/answer.py` (R-OBS-04). When an answer is wrong, these fields show five of the six
failure stages.

| Field | Meaning |
| --- | --- |
| `request_id` | Correlation |
| `outcome` | `answered`, `abstained`, `fallback` or `cached` |
| `abstained` | Boolean, required by §4.8 |
| `abstain_reason`, `fallback_reason` | When applicable |
| `top_k` | The k used |
| `chunk_ids` | Retrieved ids, in rank order |
| `scores` | Their cosine similarities, rounded to 4 decimals |
| `superseded_flags` | `superseded` value of each retrieved chunk, which shows stage E |
| `max_score`, `relevance_floor` | Why the floor did or did not trigger |
| `follow_up`, `history_turns` (count used), `include_superseded`, `hybrid`, `exact_terms` (count) | Intent flags |
| `cached`, `cache_score` | Cache outcome |
| `attempts`, `citations_valid`, `citations_dropped` | Generation quality |
| `tokens_in`, `tokens_out` | From the provider |
| `embed_ms`, `retrieval_ms`, `generation_ms` | Stage timings |
| `index_version`, `provider`, `model` | What served the request |
| `question_sha256`, `question_chars` | Question identity without its text (P3) |

## Metrics

`GET /metrics` on each api pod, in Prometheus text format (R-OBS-03). No Prometheus server is
deployed, because the brief does not ask for one. Evidence is collected with
`kubectl port-forward deploy/api 8000 -n rahbar`, then `curl localhost:8000/metrics`.

| Metric | Type | Labels | §4.8 item |
| --- | --- | --- | --- |
| `rahbar_requests_total` | counter | path, status | Request count (given) |
| `rahbar_request_seconds` | histogram | path | Request latency (given) |
| `rahbar_retrieval_seconds` | histogram | (none) | Retrieval latency |
| `rahbar_generation_seconds` | histogram | (none) | Generation latency (all attempts in a request) |
| `rahbar_embedding_seconds` | histogram | (none) | (extra) query embedding latency |
| `rahbar_cache_lookups_total` | counter | result = hit, miss, skipped | Counts behind the hit ratio |
| `rahbar_cache_hit_ratio` | gauge | (none) | Cache hit ratio: hits ÷ (hits + misses) since the pod started |
| `rahbar_abstentions_total` | counter | reason = relevance_floor, model | Abstention count |
| `rahbar_fallbacks_total` | counter | reason | Fallback count |
| `rahbar_llm_tokens_total` | counter | direction = in, out | Running token totals |
| `rahbar_llm_tokens_per_request` | histogram | direction = in, out | Tokens in and out per request |
| `rahbar_citations_dropped_total` | counter | (none) | (extra) fabricated citations removed |
| `rahbar_dependency_errors_total` | counter | dependency = chroma, redis, groq | (extra) |
| `rahbar_inflight_requests` | gauge | (none) | (extra) the signal for Engineering Note Q3 |
| `rahbar_index_info` | gauge, always 1 | index_version, embed_model | (extra) what each pod is serving |

**Engineering Note Q3 (§4.5).** While the api waits on Groq, its CPU stays low, so the
CPU-based HPA mostly measures query embedding and JSON handling, not the waiting.
`rahbar_inflight_requests` is the signal that tracks load on a generation service. To scale on
it you would need Prometheus plus prometheus-adapter or KEDA, which this design leaves out. The
team writes the answer with their own measurements.

## Diagnosing by stage

From the RAG lecture: only F is the model's fault, so check A to E first. FAILURE-ANALYSIS.md
uses this table for "how would we have noticed".

| Stage | First signal | Where |
| --- | --- | --- |
| A Extraction | A document with `chunks=0` or very few in the `chunked` log line; `ocr` pages missing; its golden questions have recall 0 | Indexer logs, `rows` in results.json |
| B Chunking | `chunk_count` and `amplification` change; per-type recall@5 drops; retrieved chunks are fragments | `indexer finished` log line, `by_type` |
| C Retrieval | `scores` low or flat in the `answered` line; recall@5 falls; or the pod is not ready because of the pin | Request log line, `/readyz` |
| D Prompt | Answers make claims no retrieved chunk supports, while citations stay valid | Manual review |
| E Source | `superseded_flags` contain `true` for questions that did not ask about an older version; version questions return old values | Request log line |
| F Generation | `rahbar_fallbacks_total` and `attempts` rise; answers vary between runs | Metrics, request log line |

## Diagnosis order

When the cluster misbehaves, always use the same order (§9). Status first, then events, then
application output.

1. `kubectl get pods -n rahbar`: which pod, and its state (`0/1`, `CrashLoopBackOff`,
   `OOMKilled`, `ImagePullBackOff`).
2. `kubectl describe pod <pod> -n rahbar`: read the **Events** at the bottom (probe failures,
   scheduling, pulls).
3. `kubectl logs <pod> -n rahbar` (add `-c fetch-corpus` for the initContainer, `--previous` for
   a crashed container). For a not-ready api pod, `curl` its `/readyz` through a port-forward to
   see which check failed.
