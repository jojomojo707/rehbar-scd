"""The query pipeline (brief section 3.2; design workflows.md § Query pipeline).

validate -> intent (follow-up?) -> embed once -> cache lookup (skipped for follow-ups) ->
retrieve -> relevance floor -> prompt -> generate -> validate, retry, fallback -> store the
turn and, when cacheable, the cache entry -> one JSON log line.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass

from ..config import Settings
from ..logjson import request_id_var
from ..providers.llm.base import LLMProvider, ProviderError
from ..retrieval.base import RetrievalQuery, Retriever
from ..routes import metrics
from ..schemas import Answer, AskResponse, HistoryTurn, Passage, RetrievedRef
from .cache import (
    NullSemanticCache,
    SemanticCache,
    cache_namespace,
    config_fingerprint,
    is_cacheable,
)
from .fallback import relevance_abstention, safe_fallback
from .prompt import PROMPT_VERSION, build_prompt
from .query_intent import (
    QueryIntent,
    classify_query,
    follow_up_retrieval_text,
    is_follow_up,
    make_retrieval_query,
    trim_history,
)
from .turns import NullTurnLog, Turn, TurnLog
from .validate import AnswerValidationError, ValidationReport, validate_answer

log = logging.getLogger("rahbar.answer")


def _index_context(retriever: Retriever) -> tuple[object | None, dict[str, object]]:
    state_reader = getattr(retriever, "index_state", None)
    if state_reader is None:
        return None, {}
    status = state_reader.current()
    return status, dict(status.metadata)


def _query_intent(question: str, metadata: dict[str, object]) -> QueryIntent:
    raw_versions = str(metadata.get("superseded_versions", ""))
    versions = [value.strip() for value in raw_versions.split(",") if value.strip()]
    return classify_query(question, versions)


def _retrieval_query(
    question: str,
    retriever: Retriever,
    settings: Settings,
    status: object | None,
    metadata: dict[str, object],
) -> RetrievalQuery | str:
    embedder = getattr(retriever, "embedder", None)
    if embedder is None:
        return question
    raw_versions = str(metadata.get("superseded_versions", ""))
    versions = [value.strip() for value in raw_versions.split(",") if value.strip()]
    collection = str(getattr(status, "active", None) or settings.collection)
    return make_retrieval_query(question, settings.top_k, collection, embedder, versions)


def _check_relevance_floor(passages: list[Passage], floor: float) -> bool:
    """Abstain when retrieval found no passage at or above the configured score floor."""
    return not passages or max(passage.score for passage in passages) < floor


def _validated_completion(
    question: str,
    passages: list[Passage],
    history: list[HistoryTurn],
    provider: LLMProvider,
    temperature: float,
    report: ValidationReport | None = None,
) -> tuple[Answer, str | None, int, int, str, int]:
    """Generate and validate at most twice, retaining aggregate provider usage."""
    messages = build_prompt(question, passages, history)
    schema = Answer.model_json_schema()
    failure_reason = "unknown"
    tokens_in = 0
    tokens_out = 0
    model = ""
    # Attempt 1, then one retry (section 3.4): with a correction turn after a validation
    # failure, after a 1 s pause after a timeout, rate limit or server error. Then fall back.
    for attempt in range(2):
        try:
            completion = provider.complete(messages, schema, temperature)
            raw_text = completion.text
            tokens_in += max(0, completion.tokens_in)
            tokens_out += max(0, completion.tokens_out)
            model = completion.model
        except ProviderError as exc:
            failure_reason = "provider"
            dependency = "groq" if provider.name == "hosted" else provider.name
            metrics.DEPENDENCY_ERRORS.labels(dependency=dependency).inc()
            if exc.kind in {"auth", "not_configured"}:
                break
            if attempt == 1:
                break
            if exc.kind in {"timeout", "rate_limited", "server"}:
                time.sleep(1)
            elif exc.kind == "bad_request":
                messages = [*messages, {
                    "role": "user",
                    "content": "Your request was rejected. Reply with JSON matching the schema "
                    "and cite only the evidence headers above.",
                }]
            continue
        except Exception as exc:
            log.error("provider call failed", extra={"error_type": type(exc).__name__})
            failure_reason = "provider"
            break

        try:
            return (
                validate_answer(raw_text, passages, report),
                None,
                tokens_in,
                tokens_out,
                model,
                attempt + 1,
            )
        except AnswerValidationError as exc:
            failure_reason = "validation"
            if attempt == 1:
                break
            log.warning("invalid model reply, one retry with a correction turn",
                        extra={"reason": exc.reason})
            messages = [
                *messages,
                {"role": "assistant", "content": raw_text},
                {
                    "role": "user",
                    "content": f"Your previous reply was rejected: {exc.reason}. Reply again "
                    "with JSON matching the schema, citing only the evidence headers above.",
                },
            ]
    return (
        safe_fallback(None, provider.name),
        failure_reason,
        tokens_in,
        tokens_out,
        model,
        attempt + 1,
    )


@dataclass(frozen=True)
class AskResult:
    """The response plus the cache outcome the route puts in the X-Cache header."""

    response: AskResponse
    cache_status: str          # HIT | MISS | SKIP


_cache_counts = {"hit": 0, "miss": 0}


def _record_cache(result: str) -> None:
    metrics.CACHE_LOOKUPS.labels(result=result).inc()
    if result in _cache_counts:
        _cache_counts[result] += 1
        total = _cache_counts["hit"] + _cache_counts["miss"]
        metrics.CACHE_HIT_RATIO.set(_cache_counts["hit"] / total if total else 0.0)


def fingerprint_for(settings: Settings) -> str:
    """The cache namespace part that changes whenever an answer-shaping setting changes."""
    return config_fingerprint({
        "PROMPT_VERSION": PROMPT_VERSION,
        "LLM_MODEL": settings.llm_model,
        "TEMPERATURE": settings.temperature,
        "TOP_K": settings.top_k,
        "RELEVANCE_FLOOR": settings.relevance_floor,
        "HYBRID_RETRIEVAL": settings.hybrid_retrieval,
        "SUPERSEDED_FILTER": settings.superseded_filter,
    })


def answer_question(
    question: str,
    retriever: Retriever,
    provider: LLMProvider,
    settings: Settings,
    history: list[HistoryTurn] | None = None,
    cache: SemanticCache | None = None,
    turns: TurnLog | None = None,
) -> AskResponse:
    """The query pipeline; see answer_with_cache_status for the X-Cache outcome."""
    return answer_with_cache_status(
        question, retriever, provider, settings, history, cache, turns
    ).response


def answer_with_cache_status(
    question: str,
    retriever: Retriever,
    provider: LLMProvider,
    settings: Settings,
    history: list[HistoryTurn] | None = None,
    cache: SemanticCache | None = None,
    turns: TurnLog | None = None,
) -> AskResult:
    cache = cache or NullSemanticCache()
    turns = turns or NullTurnLog()
    request_id = request_id_var.get()

    # 1. Validate: FastAPI/Pydantic checked the caps (422); trimming never fails.
    history = trim_history(history or [], settings.history_max_turns,
                           settings.history_answer_max_chars)
    # 2. Intent. A follow-up refers back to the history (D4, ADR 0005). Only follow-ups use it.
    status, metadata = _index_context(retriever)
    follow_up = is_follow_up(question, history)
    skip_cache = follow_up                      # never look up or store a follow-up (3.3)
    used_history = history if follow_up else []
    retrieval_text = follow_up_retrieval_text(question, history) if follow_up else question
    intent = _query_intent(retrieval_text, metadata)
    # 3. Embed once; the vector serves both the cache and retrieval.
    embed_started = time.perf_counter()
    query = _retrieval_query(retrieval_text, retriever, settings, status, metadata)
    embed_ms = round((time.perf_counter() - embed_started) * 1000, 1)
    vector = query.vector if isinstance(query, RetrievalQuery) else []
    include_superseded = (
        query.include_superseded if isinstance(query, RetrievalQuery)
        else intent.include_superseded
    )
    index_version = str(getattr(status, "active", None) or "") or None
    namespace = cache_namespace(index_version or settings.collection, fingerprint_for(settings),
                                include_superseded)

    metrics.INFLIGHT.inc()
    try:
        common = {
            "retriever": retriever.name,
            "provider": provider.name,
            "top_k": settings.top_k,
            "follow_up": follow_up,
            "history_turns": len(used_history),
            "include_superseded": include_superseded,
            "hybrid": settings.hybrid_retrieval,
            "exact_terms": len(intent.exact_terms),
            "relevance_floor": settings.relevance_floor,
            "index_version": index_version or "unknown",
            "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest()[:12],
            "question_chars": len(question),
            "embed_ms": embed_ms,
        }

        # 2 (after 3). Cache lookup, unless this is a follow-up or there is no index version.
        cache_status = "SKIP"
        if not skip_cache and index_version and vector:
            hit = cache.lookup(namespace, vector)
            if hit is not None:
                _record_cache("hit")
                response = hit.response.model_copy(
                    update={"request_id": request_id, "cached": True})
                turns.append(Turn(question=question, answer=response.answer,
                                  request_id=request_id,
                                  answered_from_context=response.answered_from_context,
                                  outcome="cached", follow_up=False, history_turns=0))
                log.info("answered", extra={
                    **common,
                    "model": settings.llm_model,
                    "outcome": "cached",
                    "abstained": not response.answered_from_context,
                    "cached": True,
                    "cache_score": round(hit.score, 4),
                    "chunk_ids": [ref.chunk_id for ref in response.retrieved],
                    "scores": [round(ref.score, 4) for ref in response.retrieved],
                    "attempts": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                })
                return AskResult(response, "HIT")
            _record_cache("miss")
            cache_status = "MISS"
        else:
            _record_cache("skip")

        # 4. Retrieve from the active index; Chroma's adapter applies the source filter.
        retrieval_started = time.perf_counter()
        if isinstance(query, RetrievalQuery):
            passages = retriever.retrieve(query)
        else:
            passages = retriever.retrieve(query, k=settings.top_k)
        retrieval_seconds = time.perf_counter() - retrieval_started
        metrics.RETRIEVAL.observe(retrieval_seconds)

        # Relevance floor, then 5. augment, 6. generate, 7. validate with retry and fallback.
        should_abstain = _check_relevance_floor(passages, settings.relevance_floor)
        fallback_reason = None
        tokens_in = 0
        tokens_out = 0
        generation_model = ""
        generation_attempts = 0
        generation_ms = 0.0
        report = ValidationReport()
        if should_abstain:
            metrics.ABSTENTIONS.labels(reason="relevance_floor").inc()
            answer = relevance_abstention()
        else:
            generation_started = time.perf_counter()
            (
                answer,
                fallback_reason,
                tokens_in,
                tokens_out,
                generation_model,
                generation_attempts,
            ) = _validated_completion(
                question,
                passages,
                used_history,
                provider,
                settings.temperature,
                report,
            )
            generation_seconds = time.perf_counter() - generation_started
            generation_ms = round(generation_seconds * 1000, 1)
            metrics.GENERATION.observe(generation_seconds)
            if fallback_reason is not None:
                metrics.FALLBACKS.labels(reason=fallback_reason).inc()
        for direction, count in (("in", tokens_in), ("out", tokens_out)):
            metrics.LLM_TOKENS.labels(direction=direction).inc(count)
            metrics.LLM_TOKENS_PER_REQUEST.labels(direction=direction).observe(count)
        abstain_reason = None
        if should_abstain:
            abstain_reason = "relevance_floor"
        elif fallback_reason is None and not answer.answered_from_context:
            abstain_reason = "model"
            metrics.ABSTENTIONS.labels(reason="model").inc()
        if fallback_reason is not None:
            outcome = "fallback"
        elif abstain_reason is not None:
            outcome = "abstained"
        else:
            outcome = "answered"

        response = AskResponse(
            request_id=request_id,
            answer=answer.answer,
            citations=answer.citations,
            answered_from_context=answer.answered_from_context,
            confidence=answer.confidence,
            retrieved=[
                RetrievedRef(
                    chunk_id=passage.chunk_id,
                    source=passage.source,
                    section=passage.section,
                    page=passage.page,
                    score=passage.score,
                )
                for passage in passages
            ],
            provider=provider.name,
            cached=False,
        )

        # 8. Store the turn (every outcome) and the cache entry (only if cacheable).
        turns.append(Turn(question=question, answer=response.answer, request_id=request_id,
                          answered_from_context=response.answered_from_context,
                          outcome=outcome, follow_up=follow_up,
                          history_turns=len(used_history)))
        if cache_status == "MISS" and is_cacheable(
            follow_up=follow_up,
            outcome=outcome,
            answered_from_context=response.answered_from_context,
            citations=len(response.citations),
            dropped_citations=report.dropped,
        ):
            cache.store(namespace, vector, question, response)

        metrics.INDEX_INFO.labels(
            index_version=index_version or "unknown", embed_model=settings.embed_model
        ).set(1)
        log.info(
            "answered",
            extra={
                **common,
                "model": generation_model or settings.llm_model,
                "chunk_ids": [passage.chunk_id for passage in passages],
                "scores": [round(passage.score, 4) for passage in passages],
                "superseded_flags": [passage.superseded for passage in passages],
                "max_score": round(max((p.score for p in passages), default=0.0), 4),
                "answered_from_context": answer.answered_from_context,
                "outcome": outcome,
                "abstained": not answer.answered_from_context,
                "abstain_reason": abstain_reason,
                "fallback_reason": fallback_reason,
                "cached": False,
                "cache_score": None,
                "attempts": generation_attempts,
                "generation_attempts": generation_attempts,
                "citations_valid": len(answer.citations),
                "citations_dropped": report.dropped_citations,
                "markers_dropped": report.dropped_markers,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "retrieval_ms": round(retrieval_seconds * 1000, 1),
                "generation_ms": generation_ms,
            },
        )
        return AskResult(response, cache_status)
    finally:
        metrics.INFLIGHT.dec()
