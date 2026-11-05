"""Shared answer-validation boundary for Day 3 generation work."""

from __future__ import annotations

from ..schemas import Answer, Passage


def validate_answer(answer: Answer, passages: list[Passage]) -> Answer:
    """Pass through the stub provider's already-typed answer in the Day 2 scaffold."""
    return answer
