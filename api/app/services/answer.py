"""Turns a question into an AskResponse. This is where the query pipeline lives.

The version below is the bare minimum that works with the stubs: retrieve,
generate, return. Section 3.2 lists eight steps; this file does two of them.
"""

from __future__ import annotations

import hashlib
import logging
import time

from ..config import Settings
from ..logjson import request_id_var
from ..providers.llm.base import LLMProvider
from ..retrieval.base import Retriever
from ..routes import metrics
from ..schemas import AskResponse, HistoryTurn, RetrievedRef

log = logging.getLogger("rahbar.answer")


def answer_question(
    question: str, retriever: Retriever, provider: LLMProvider, settings: Settings,
    history: list[HistoryTurn] | None = None,
) -> AskResponse:
    # STARTER-TODO(3.2-3.4): add the production steps around these two calls:
    # the semantic cache (3.3), the relevance floor and honest abstention (3.4),
    # validation with one retry and a safe fallback (3.4), and the check that every
    # citation matches a retrieved passage (3.4). Keep this function thin: put each
    # step in its own module under services/ so each can be unit-tested.
    history = history or []
    metrics.INFLIGHT.inc()
    metrics.CACHE_LOOKUPS.labels(result="skipped").inc()
    try:
        started = time.perf_counter()
        passages = retriever.retrieve(question, k=settings.top_k)
        metrics.RETRIEVAL.observe(time.perf_counter() - started)

        started = time.perf_counter()
        answer = provider.generate(question, passages)
        metrics.GENERATION.observe(time.perf_counter() - started)
        if not answer.answered_from_context:
            metrics.ABSTENTIONS.labels(reason="model").inc()
        index_version = "unknown"
        metrics.INDEX_INFO.labels(index_version=index_version, embed_model=settings.embed_model).set(1)

        question_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()[:12]
        log.info(
            "answered",
            extra={
                "retriever": retriever.name,
                "provider": provider.name,
                "top_k": settings.top_k,
                "chunk_ids": [p.chunk_id for p in passages],
                "scores": [round(p.score, 4) for p in passages],
                "answered_from_context": answer.answered_from_context,
                "outcome": "answered" if answer.answered_from_context else "abstained",
                "abstained": not answer.answered_from_context,
                "history_turns": len(history),
                "follow_up": bool(history),
                "cached": False,
                "question_sha256": question_hash,
                "question_chars": len(question),
            },
        )
        return AskResponse(
            request_id=request_id_var.get(),
            answer=answer.answer,
            citations=answer.citations,
            answered_from_context=answer.answered_from_context,
            confidence=answer.confidence,
            retrieved=[
                RetrievedRef(
                    chunk_id=p.chunk_id, source=p.source, section=p.section, page=p.page, score=p.score
                )
                for p in passages
            ],
            provider=provider.name,
        )
    finally:
        metrics.INFLIGHT.dec()
