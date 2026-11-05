"""Prompt construction boundary; implementation lands with generation work."""

from __future__ import annotations

from ..schemas import HistoryTurn, Passage


def build_prompt(
    question: str,
    passages: list[Passage],
    history: list[HistoryTurn] | None = None,
) -> list[dict[str, str]]:
    """Return no messages in the Day 2 scaffold; the stub provider still takes raw context."""
    return []
