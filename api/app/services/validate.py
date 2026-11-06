"""Parse model output and enforce schema and request-local citation rules."""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from ..routes import metrics
from ..schemas import Answer, Passage

_INLINE_CITATION = re.compile(r"\[([^\]/]+?)\s*/\s*([^\]]+?)\]")
ABSTENTION_TEXT = (
    "The documents I have do not cover this question, so I can't answer it from them."
)


class AnswerValidationError(ValueError):
    """A model reply that should be retried once with a correction prompt."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def validate_answer(answer: str | dict[str, object] | Answer, passages: list[Passage]) -> Answer:
    """Validate JSON, normalize abstentions, and remove unsupported citations."""
    if isinstance(answer, Answer):
        candidate: object = answer.model_dump()
    elif isinstance(answer, str):
        try:
            candidate = json.loads(answer)
        except (json.JSONDecodeError, TypeError) as exc:
            raise AnswerValidationError("invalid_json", "The reply was not valid JSON.") from exc
    else:
        candidate = answer

    try:
        parsed = Answer.model_validate(candidate)
    except (ValidationError, TypeError, ValueError) as exc:
        raise AnswerValidationError(
            "schema", "The reply did not match the Answer schema."
        ) from exc

    text = parsed.answer.strip()
    if not text or len(text) > 4000:
        raise AnswerValidationError("schema", "The answer must contain 1 to 4000 characters.")

    if not parsed.answered_from_context:
        return Answer(
            reasoning="",
            answer=ABSTENTION_TEXT,
            citations=[],
            answered_from_context=False,
            confidence="low",
        )

    by_key = {(p.source, p.section): p for p in passages}
    valid_citations = []
    for citation in parsed.citations:
        passage = by_key.get((citation.source, citation.section))
        if passage is not None and (citation.page is None or citation.page == passage.page):
            valid_citations.append(citation)
        else:
            metrics.CITATIONS_DROPPED.inc()

    valid_keys = {(citation.source, citation.section) for citation in valid_citations}

    def keep_inline(match: re.Match[str]) -> str:
        key = (match.group(1).strip(), match.group(2).strip())
        return match.group(0) if key in valid_keys else ""

    cleaned_text = _INLINE_CITATION.sub(keep_inline, text)
    cleaned_text = re.sub(r"[ \t]{2,}", " ", cleaned_text).strip()
    if not valid_citations:
        raise AnswerValidationError("no_valid_citation", "No citation matched retrieved evidence.")
    if not cleaned_text:
        raise AnswerValidationError("schema", "No answer text remains after citation checks.")
    if not _INLINE_CITATION.search(cleaned_text):
        raise AnswerValidationError("no_inline_citation", "The answer has no valid inline citation.")

    return parsed.model_copy(
        update={
            "reasoning": "",
            "answer": cleaned_text,
            "citations": valid_citations,
        }
    )
