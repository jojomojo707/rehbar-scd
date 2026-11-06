"""Query intent before retrieval: explicit older versions, exact terms, and follow-ups.

Follow-up rules are D4 / workflows.md § Follow-up questions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..providers.embedding.base import Embedder
from ..retrieval.base import RetrievalQuery
from ..schemas import HistoryTurn


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


# A follow-up starts with one of these phrases ...
_FOLLOW_UP_START = re.compile(r"^(and|also|so|what about|how about|then|but|what if)\b", re.I)
# ... or has a referring word among its first three words. "there" is not one: "Is there a
# late fee?" is a new question.
_REFERRING_WORDS = frozenset({"it", "its", "that", "this", "those", "these", "they", "them"})
_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")


def trim_history(
    history: list[HistoryTurn], max_turns: int, answer_max_chars: int
) -> list[HistoryTurn]:
    """Keep the newest `max_turns` turns (oldest first) and cut each answer. Never fails."""
    if max_turns <= 0:
        return []
    return [
        turn.model_copy(update={"answer": turn.answer[: max(0, answer_max_chars)]})
        for turn in history[-max_turns:]
    ]


def is_follow_up(question: str, history: list[HistoryTurn]) -> bool:
    """True only when there is history AND the question's start refers back to it.

    Only the start is checked, so "What is the fee that applies to MS students?" is not a
    follow-up even though it contains "that".
    """
    if not history:
        return False
    text = question.strip()
    if _FOLLOW_UP_START.match(text):
        return True
    first_words = [word.replace("'s", "s") for word in _WORD.findall(text.lower())[:3]]
    return any(word in _REFERRING_WORDS for word in first_words)


def follow_up_retrieval_text(question: str, history: list[HistoryTurn]) -> str:
    """The last history question, a newline, then the new question (workflows.md)."""
    return f"{history[-1].question}\n{question}" if history else question
