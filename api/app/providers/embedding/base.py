"""Query embedder contract."""

from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dimension: int

    def embed_query(self, text: str) -> list[float]: ...
