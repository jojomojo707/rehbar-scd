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
    """kind: auth, not_configured, rate_limited, timeout, server or bad_request.
    retry_after: seconds the provider asked us to wait (rate limits), when it said."""

    def __init__(self, kind: str, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.retry_after = retry_after


class LLMProvider(Protocol):
    name: str

    def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any], temperature: float
    ) -> Completion:
        """Return raw model text and usage; the shared pipeline validates the answer."""
        ...
