"""Conversation history and follow-up detection (3A2; D4, workflows.md § Follow-up questions)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import get_settings
from app.main import app
from app.schemas import AskRequest, HistoryTurn
from app.services.query_intent import follow_up_retrieval_text, is_follow_up, trim_history

ONE_TURN = [HistoryTurn(question="What is the BS fee per credit hour?", answer="10,000 [f / 1]")]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # starts with a follow-up phrase
        ("And for MS students?", True),
        ("also the late fee?", True),
        ("So what happens then?", True),
        ("What about MS students?", True),
        ("How about the summer semester?", True),
        ("Then what is the deadline?", True),
        ("But is it the same for MS?", True),
        ("What if I fail twice?", True),
        # a referring word among the first three words
        ("Does it apply to MS?", True),
        ("Is that per semester?", True),
        ("Are those fees refundable?", True),
        ("Can they waive it?", True),
        ("Is it's deadline fixed?", True),
        # new questions
        ("What is the minimum attendance?", False),
        ("What is the fee that applies to MS students?", False),   # "that" is word 5
        ("Is there a late fee?", False),                           # "there" is not referring
        ("Android course fee?", False),                            # "and" only as a prefix
        ("Somewhere in the handbook, what is clause 1.22?", False),  # "so" only as a prefix
        ("Then", True),
    ],
)
def test_followup_detection(question: str, expected: bool) -> None:
    assert is_follow_up(question, ONE_TURN) is expected


def test_no_history_is_never_a_follow_up() -> None:
    assert is_follow_up("And for MS students?", []) is False
    assert is_follow_up("Does it apply to MS?", []) is False


def test_history_limits() -> None:
    turns = [HistoryTurn(question=f"question {i}", answer="x" * 1000) for i in range(5)]
    trimmed = trim_history(turns, max_turns=3, answer_max_chars=600)
    assert [turn.question for turn in trimmed] == ["question 2", "question 3", "question 4"]
    assert all(len(turn.answer) == 600 for turn in trimmed)
    assert turns[4].answer == "x" * 1000                 # the request's own list is untouched
    assert trim_history(turns, max_turns=0, answer_max_chars=600) == []


def test_history_caps_return_422_not_trim() -> None:
    AskRequest(question="What is it?", history=[{"question": "abc", "answer": "a"}] * 10)
    with pytest.raises(ValidationError):
        AskRequest(question="What is it?", history=[{"question": "abc", "answer": "a"}] * 11)
    with pytest.raises(ValidationError):
        AskRequest(question="What is it?", history=[{"question": "abc", "answer": "a" * 2001}])
    with pytest.raises(ValidationError):
        AskRequest(question="What is it?", history=[{"question": "q" * 501, "answer": "a"}])


def test_follow_up_retrieval_text_prepends_the_last_question() -> None:
    history = [HistoryTurn(question="first?", answer="a"), *ONE_TURN]
    assert follow_up_retrieval_text("And for MS?", history) == (
        "What is the BS fee per credit hour?\nAnd for MS?")
    assert follow_up_retrieval_text("Plain question?", []) == "Plain question?"


def test_history_settings_come_from_the_configmap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HISTORY_MAX_TURNS", "2")
    monkeypatch.setenv("HISTORY_ANSWER_MAX_CHARS", "100")
    settings = get_settings()
    assert (settings.history_max_turns, settings.history_answer_max_chars) == (2, 100)


def test_ask_accepts_history_from_the_browser() -> None:
    with TestClient(app) as client:
        res = client.post("/api/ask", json={
            "question": "What about MS students?",
            "history": [{"question": "What is the BS fee?", "answer": "10,000"}] * 4,
        })
    assert res.status_code == 200
