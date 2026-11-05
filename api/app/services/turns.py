"""Conversation turn-log contract and no-op scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Turn:
    question: str
    answer: str


class TurnLog(Protocol):
    def append(self, turn: Turn) -> None: ...


class NullTurnLog:
    def append(self, turn: Turn) -> None:
        return None
