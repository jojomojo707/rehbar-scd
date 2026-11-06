"""The LLM provider interface (section 3.5). Swapping providers is one file."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

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

    def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any], temperature: float
    ) -> Completion:
        """Return raw model text and usage; the shared pipeline validates the answer."""
        ...
