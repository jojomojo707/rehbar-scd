"""Extract explicit historical-version intent before retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..providers.embedding.base import Embedder
from ..retrieval.base import RetrievalQuery


@dataclass(frozen=True)
class QueryIntent:
    include_superseded: bool
    requested_year: str | None
    exact_terms: list[str]


_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_QUOTED = re.compile(r"[\"“”']([^\"“”']{2,80})[\"“”']")
_HISTORICAL_CUES = re.compile(r"\b(old|older|previous|former|superseded|historical|before|prior|last year)\b", re.I)


def classify_query(text: str) -> QueryIntent:
    year = _YEAR.search(text)
    quoted = [value.strip() for value in _QUOTED.findall(text) if value.strip()]
    acronyms = re.findall(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)*\b", text)
    terms = list(dict.fromkeys([*quoted, *acronyms]))
    return QueryIntent(
        include_superseded=bool(year or _HISTORICAL_CUES.search(text)),
        requested_year=year.group(0) if year else None,
        exact_terms=terms,
    )


def make_retrieval_query(text: str, k: int, collection: str, embedder: Embedder) -> RetrievalQuery:
    intent = classify_query(text)
    return RetrievalQuery(
        text=text,
        vector=embedder.embed_query(text),
        k=k,
        include_superseded=intent.include_superseded,
        exact_terms=intent.exact_terms,
        collection=collection,
        requested_year=intent.requested_year,
    )
