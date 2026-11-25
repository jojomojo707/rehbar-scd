"""Retrieval rail: screen retrieved passages for injected instructions (RAGOps Table 2,
observability: "injection attack detection").

The corpus is untrusted text. A passage can carry an instruction aimed at the model ("ignore
all previous instructions..."), as the Batch B document `it-acceptable-use-policy.md` does.
Before the prompt is built, each sentence that matches an override pattern is removed from the
passage. The passage stays (its other sentences are still evidence) unless nothing is left.
Every removal is returned so the caller can write it into the trace and count it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..schemas import Passage

_INJECTION = re.compile(
    r"\b(?:ignore|disregard|override|bypass|forget)\b.{0,80}\b"
    r"(?:rules?|instructions?|prompts?|grounding|guidelines|context)\b|"
    r"\b(?:reveal|print|show|expose|leak)\b.{0,80}\b(?:hidden|system|secret)\s+prompt\b|"
    r"\b(?:system|developer)\s+(?:notice|message|instruction)s?\s+(?:to|for)\s+the\s+"
    r"(?:ai|assistant|model|llm)\b|"
    r"\byou\s+are\s+now\b.{0,60}\b(?:assistant|ai|model|mode)\b",
    re.IGNORECASE | re.DOTALL,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class InjectionFlag:
    chunk_id: str
    document: str
    removed: str          # the sentence that was taken out (first 160 characters)
    dropped_passage: bool


def screen_passages(passages: list[Passage]) -> tuple[list[Passage], list[InjectionFlag]]:
    kept: list[Passage] = []
    flags: list[InjectionFlag] = []
    for passage in passages:
        if not _INJECTION.search(passage.text):
            kept.append(passage)
            continue
        pieces = [piece for piece in _SENTENCE.split(passage.text) if piece.strip()]
        bad = [piece for piece in pieces if _INJECTION.search(piece)]
        good = [piece for piece in pieces if not _INJECTION.search(piece)]
        cleaned = " ".join(good).strip()
        dropped = not cleaned
        for sentence in bad or [passage.text]:
            flags.append(InjectionFlag(passage.chunk_id, passage.source,
                                       " ".join(sentence.split())[:160], dropped))
        if not dropped:
            kept.append(passage.model_copy(update={"text": cleaned}))
    return kept, flags
