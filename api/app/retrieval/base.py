"""The retriever interface. The rest of the API only ever sees this."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..schemas import Passage


@dataclass(frozen=True)
class RetrievalQuery:
    text: str
    vector: list[float]
    k: int
    include_superseded: bool = False
    exact_terms: list[str] = field(default_factory=list)
    collection: str = ""
    requested_year: str | None = None


class Retriever(Protocol):
    name: str

    def retrieve(self, query: RetrievalQuery | str, k: int | None = None) -> list[Passage]:
        """Return up to k passages, best first."""
        ...
