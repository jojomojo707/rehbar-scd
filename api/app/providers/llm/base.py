"""The LLM provider interface (section 3.5). Swapping providers is one file."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...schemas import Answer, Passage


@dataclass(frozen=True)
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    model: str


class ProviderError(RuntimeError):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class LLMProvider(Protocol):
    name: str

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        """Answer the question from the passages, as an `Answer`."""
        ...
