"""Safe fallback boundary used after a generation/validation failure."""

from __future__ import annotations

from ..schemas import Answer

FALLBACK_TEXT = (
    "I couldn't produce a reliable, cited answer right now. Please try again in a moment."
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
