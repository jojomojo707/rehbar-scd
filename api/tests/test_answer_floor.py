from app.config import Settings
from app.providers.llm.base import Completion
from app.schemas import Answer, Citation, Passage
from app.services.answer import answer_question
from app.services.validate import ABSTENTION_TEXT


class FakeRetriever:
    name = "fake"

    def __init__(self, passages: list[Passage]) -> None:
        self.passages = passages

    def retrieve(self, query, k=None):
        del query, k
        return self.passages


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages, schema, temperature):
        del messages, schema, temperature
        self.calls += 1
        answer = Answer(
            reasoning="",
            answer="The rule is in the handbook [handbook.pdf / 5.4 Academic Warning]",
            citations=[Citation(source="handbook.pdf", section="5.4 Academic Warning", page=31)],
            answered_from_context=True,
            confidence="medium",
        )
        return Completion(answer.model_dump_json(), tokens_in=10, tokens_out=5, model="fake")


def make_passage(score: float) -> Passage:
    return Passage(
        chunk_id="handbook:00001",
        text="The rule is described here.",
        source="handbook.pdf",
        section="5.4 Academic Warning",
        page=31,
        score=score,
    )


def test_relevance_floor_abstains_without_calling_provider() -> None:
    provider = FakeProvider()
    response = answer_question(
        "What does academic warning mean?",
        FakeRetriever([make_passage(0.72854733)]),
        provider,
        Settings(relevance_floor=0.729),
    )

    assert provider.calls == 0
    assert response.answered_from_context is False
    assert response.answer == ABSTENTION_TEXT
    assert response.citations == []
    assert len(response.retrieved) == 1


def test_relevance_floor_accepts_a_passage_at_the_threshold() -> None:
    provider = FakeProvider()
    response = answer_question(
        "What does academic warning mean?",
        FakeRetriever([make_passage(0.729)]),
        provider,
        Settings(relevance_floor=0.729),
    )

    assert provider.calls == 1
    assert response.answered_from_context is True
