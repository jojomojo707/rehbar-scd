"""Semantic cache contract and no-op scaffold for later pipeline work."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..schemas import AskResponse


@dataclass(frozen=True)
class CacheHit:
    response: AskResponse
    score: float


class SemanticCache(Protocol):
    def lookup(self, namespace: str, vector: list[float]) -> CacheHit | None: ...

    def store(self, namespace: str, vector: list[float], question: str, response: AskResponse) -> None: ...

    def invalidate_except(self, index_version: str) -> int: ...


class NullSemanticCache:
    """Disabled cache used until Redis wiring is implemented."""

    def lookup(self, namespace: str, vector: list[float]) -> None:
        return None

    def store(self, namespace: str, vector: list[float], question: str, response: AskResponse) -> None:
        return None

    def invalidate_except(self, index_version: str) -> int:
        return 0
