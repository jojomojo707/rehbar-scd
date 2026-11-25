"""Append privacy-filtered, reconstructable per-request traces as JSONL."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import socket
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..schemas import HistoryTurn
from .prompt import build_prompt

log = logging.getLogger("rahbar.trace")
_LOCK = threading.Lock()
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)")


def redact(value: str) -> str:
    """Mask common direct identifiers before writing user or corpus text to disk."""
    return _PHONE.sub("[REDACTED_PHONE]", _EMAIL.sub("[REDACTED_EMAIL]", value))


def write_trace(directory: str, trace: dict[str, Any]) -> None:
    if not directory:
        return
    now = datetime.now(timezone.utc)
    safe_trace = redact_tree(trace)
    safe_trace.setdefault("timestamp", now.isoformat())
    safe_trace.setdefault("pod", socket.gethostname())
    path = Path(directory) / f"api-{socket.gethostname()}-{now:%Y%m%d}.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(safe_trace, ensure_ascii=False, separators=(",", ":"), default=str)
        log.info("query trace", extra={"trace": safe_trace})
        with _LOCK, path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
    except OSError:
        log.exception("could not persist query trace", extra={"trace_id": trace.get("trace_id")})


@lru_cache(maxsize=4)
def embedding_version(model: str, cache_dir: str) -> str:
    """The pinned model's version: its Hugging Face snapshot revision and ONNX file digest."""
    files = sorted(Path(cache_dir).glob("**/snapshots/*/*.onnx")) if cache_dir else []
    if not files:
        return f"{model}@unknown"
    onnx = files[0]
    digest = hashlib.sha256(onnx.resolve().read_bytes()).hexdigest()[:16]
    return f"{model}@{onnx.parent.name[:12]}/onnx-sha256:{digest}"


def redact_tree(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [redact_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_tree(item) for key, item in value.items()}
    return value


def make_trace(*, trace_id: str, question: str, retrieval_query: str,
               passages: list[Any], response: Any, settings: Any,
               index_version: str | None, cache_status: str,
               stage_ms: dict[str, float], guardrail_actions: list[str],
               history: list[HistoryTurn] | None = None,
               generated: bool = True, outcome: str | None = None,
               fallback_reason: str | None = None,
               abstain_reason: str | None = None,
               retrieved_passages: list[Any] | None = None,
               injection_flags: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    safe_question = redact(question)
    def scored(items: list[Any]) -> list[dict[str, Any]]:
        return [{"chunk_id": p.chunk_id, "document": p.source, "version": p.doc_version,
                 "score": p.score} for p in items]

    safe_passages = [{
        "chunk_id": p.chunk_id, "document": p.source, "version": p.doc_version,
        "section": p.section, "page": p.page, "score": p.score,
        "superseded": p.superseded, "text": redact(p.text),
    } for p in passages]
    if not passages:
        safe_passages = [{"chunk_id": ref.chunk_id, "document": ref.source,
                          "version": "unknown-cache-entry", "section": ref.section,
                          "page": ref.page, "score": ref.score, "superseded": None,
                          "text": None} for ref in response.retrieved]
    prompt_passages = [p.model_copy(update={"text": redact(p.text)}) for p in passages]
    safe_history = [turn.model_copy(update={"question": redact(turn.question),
                                           "answer": redact(turn.answer)})
                    for turn in (history or [])]
    prompt = build_prompt(safe_question, prompt_passages, safe_history) if passages and generated else []
    prompt_json = json.dumps(prompt, ensure_ascii=False, sort_keys=True)
    return {
        "trace_id": trace_id,
        "query": safe_question,
        "rewrite": redact(retrieval_query),
        "embedding_model": settings.embed_model,
        "embedding_version": embedding_version(settings.embed_model, settings.embed_cache_dir),
        "collection": settings.collection,
        "collection_version": index_version,
        "retrieved_before_guardrails": scored(retrieved_passages or []),
        "retrieved": safe_passages,
        "filters": {"superseded_filter": settings.superseded_filter},
        "rerank_order": [p["chunk_id"] for p in safe_passages],
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt_json.encode("utf-8")).hexdigest() if prompt else None,
        "model_parameters": {"provider": settings.llm_provider, "model": settings.llm_model,
                             "temperature": settings.temperature, "top_k": settings.top_k,
                             "max_tokens": settings.llm_max_tokens,
                             "reasoning_effort": settings.llm_reasoning_effort,
                             "seed": getattr(settings, "llm_seed", None)},
        "response": {"answer": response.answer, "citations": [c.model_dump() for c in response.citations],
                     "answered_from_context": response.answered_from_context,
                     "cached": response.cached},
        "citations": [c.model_dump() for c in response.citations],
        "guardrail_actions": guardrail_actions,
        "injection_flags": injection_flags or [],
        "outcome": outcome,
        "fallback_reason": fallback_reason,
        "abstain_reason": abstain_reason,
        "stage_ms": stage_ms,
        "cache_status": cache_status,
    }
