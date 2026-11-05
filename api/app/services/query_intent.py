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
_HISTORICAL_CUES = re.compile(
    r"\b(old|older|previous|earlier|former|superseded|outdated|repealed|last year)\b", re.I
)
_EXACT_TERM = re.compile(
    r"\b\d+(?:\.\d+)+\b|\b[A-Z]{2,4}-?\d{3,4}\b|"
    r"\b\d{1,3}(?:,\d{3})+\b|\b\d{1,3}\s?%(?!\w)"
)


def classify_query(text: str, superseded_versions: list[str] | None = None) -> QueryIntent:
    year = _YEAR.search(text)
    superseded_years = {
        match.group(0)
        for version in superseded_versions or []
        for match in _YEAR.finditer(version)
    }
    requested_year = year.group(0) if year else None
    terms = list(dict.fromkeys(match.group(0) for match in _EXACT_TERM.finditer(text)))[:3]
    return QueryIntent(
        include_superseded=bool(
            _HISTORICAL_CUES.search(text)
            or (requested_year and requested_year in superseded_years)
        ),
        requested_year=requested_year,
        exact_terms=terms,
    )


def make_retrieval_query(
    text: str,
    k: int,
    collection: str,
    embedder: Embedder,
    superseded_versions: list[str] | None = None,
) -> RetrievalQuery:
    intent = classify_query(text, superseded_versions)
    return RetrievalQuery(
        text=text,
        vector=embedder.embed_query(text),
        k=k,
        include_superseded=intent.include_superseded,
        exact_terms=intent.exact_terms,
        collection=collection,
        requested_year=intent.requested_year,
    )
