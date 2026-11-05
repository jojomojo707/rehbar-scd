from app.schemas import Answer, AskResponse
from app.services.cache import NullSemanticCache
from app.services.fallback import FALLBACK_TEXT, safe_fallback
from app.services.prompt import build_prompt
from app.services.turns import NullTurnLog, Turn
from app.services.validate import validate_answer


def test_day_two_pipeline_boundaries_are_safe_noops() -> None:
    cache = NullSemanticCache()
    assert cache.lookup("rahbar-v1", []) is None
    response = AskResponse(
        request_id="test", answer="answer", citations=[], answered_from_context=True,
        confidence="high", retrieved=[], provider="stub",
    )
    cache.store("rahbar-v1", [], "question", response)
    NullTurnLog().append(Turn("question", "answer"))

    candidate = Answer(
        reasoning="", answer="answer", citations=[], answered_from_context=True,
        confidence="high",
    )
    assert build_prompt("question", []) == []
    assert validate_answer(candidate, []) is candidate
    assert safe_fallback(candidate, "stub") is candidate

    fallback = safe_fallback(None, "stub")
    assert fallback.answer == FALLBACK_TEXT
    assert fallback.answered_from_context is False
