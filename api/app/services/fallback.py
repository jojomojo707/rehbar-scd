"""Safe fallback boundary used after a generation/validation failure."""

from __future__ import annotations

from ..schemas import Answer
from .validate import ABSTENTION_TEXT

FALLBACK_TEXT = (
    "I couldn't produce a reliable, cited answer right now. Please try again in a moment."
)


def relevance_abstention() -> Answer:
    """Return the canonical abstention used when retrieval is below the score floor."""
    return Answer(
        reasoning="",
        answer=ABSTENTION_TEXT,
        citations=[],
        answered_from_context=False,
        confidence="low",
    )


def safe_fallback(answer: Answer | None, provider: str) -> Answer:
    """Keep a validated answer or return the standard safe failure response."""
    if answer is not None:
        return answer
    return Answer(
        reasoning="",
        answer=FALLBACK_TEXT,
        citations=[],
        answered_from_context=False,
        confidence="low",
    )
