"""The eight-stage request pipeline scaffold for Day 2.

Cache, follow-up, prompt validation, and turn persistence remain no-op scaffolds;
later tasks can fill them in behind these module boundaries.
"""

from __future__ import annotations

import hashlib
import logging
import time

from ..config import Settings
from ..logjson import request_id_var
from ..providers.llm.base import LLMProvider
from ..retrieval.base import RetrievalQuery, Retriever
from ..routes import metrics
from ..schemas import AskResponse, HistoryTurn, Passage, RetrievedRef
from .cache import NullSemanticCache
from .fallback import safe_fallback
from .prompt import build_prompt
from .query_intent import QueryIntent, classify_query, make_retrieval_query
from .turns import NullTurnLog, Turn
from .validate import validate_answer

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


def _check_relevance_floor(passages: list[Passage]) -> bool:
    """Day 2 placeholder: leave relevance-floor decisions to the later answer task."""
    return False


def answer_question(
    question: str,
    retriever: Retriever,
    provider: LLMProvider,
    settings: Settings,
    history: list[HistoryTurn] | None = None,
) -> AskResponse:
    # 1. Validate request/history: FastAPI/Pydantic has validated the request schema.
    history = history or []
    # 2. Intent: keep explicit-version and exact-term intent separate from follow-up (stubbed off).
    status, metadata = _index_context(retriever)
    intent = _query_intent(question, metadata)
    follow_up = False
    # 3. Embed once. The Chroma adapter owns the pinned embedder; the stub path needs no vector.
    query = _retrieval_query(question, retriever, settings, status, metadata)
    vector = query.vector if isinstance(query, RetrievalQuery) else []
    namespace = query.collection if isinstance(query, RetrievalQuery) else settings.collection

    metrics.INFLIGHT.inc()
    try:
        cache = NullSemanticCache()
        # 4. Cache lookup (scaffold always misses).
        cached = cache.lookup(namespace, vector)
        if cached is None:
            metrics.CACHE_LOOKUPS.labels(result="miss").inc()
            metrics.CACHE_HIT_RATIO.set(0.0)
        else:
            metrics.CACHE_LOOKUPS.labels(result="hit").inc()
            cache_response = cached.response.model_copy(update={"cached": True})
            return cache_response

        # 5. Retrieve from the active index; Chroma's adapter applies the source filter.
        retrieval_started = time.perf_counter()
        if isinstance(query, RetrievalQuery):
            passages = retriever.retrieve(query)
        else:
            passages = retriever.retrieve(query, k=settings.top_k)
        metrics.RETRIEVAL.observe(time.perf_counter() - retrieval_started)

        # 6. Relevance floor (no-op today), then 7. augment, generate, validate, and fallback.
        should_abstain = _check_relevance_floor(passages)
        if should_abstain:
            metrics.ABSTENTIONS.labels(reason="relevance_floor").inc()
            answer = safe_fallback(None, provider.name)
        else:
            build_prompt(question, passages, history if follow_up else [])
            generation_started = time.perf_counter()
            raw_answer = provider.generate(question, passages)
            metrics.GENERATION.observe(time.perf_counter() - generation_started)
            answer = validate_answer(raw_answer, passages)
            answer = safe_fallback(answer, provider.name)
        if not answer.answered_from_context:
            metrics.ABSTENTIONS.labels(reason="model").inc()

        # 8. Store turn and cache result (both no-op scaffolds on Day 2).
        response = AskResponse(
            request_id=request_id_var.get(),
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
        NullTurnLog().append(Turn(question=question, answer=answer.answer))
        cache.store(namespace, vector, question, response)

        index_version = str(getattr(status, "active", "unknown") or "unknown")
        metrics.INDEX_INFO.labels(
            index_version=index_version, embed_model=settings.embed_model
        ).set(1)
        question_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()[:12]
        log.info(
            "answered",
            extra={
                "retriever": retriever.name,
                "provider": provider.name,
                "top_k": settings.top_k,
                "chunk_ids": [passage.chunk_id for passage in passages],
                "scores": [round(passage.score, 4) for passage in passages],
                "answered_from_context": answer.answered_from_context,
                "outcome": "answered" if answer.answered_from_context else "abstained",
                "abstained": not answer.answered_from_context,
                "history_turns": len(history) if follow_up else 0,
                "follow_up": follow_up,
                "include_superseded": intent.include_superseded,
                "exact_terms": len(intent.exact_terms),
                "cached": False,
                "cache_score": None,
                "index_version": index_version,
                "question_sha256": question_hash,
                "question_chars": len(question),
            },
        )
        return response
    finally:
        metrics.INFLIGHT.dec()
