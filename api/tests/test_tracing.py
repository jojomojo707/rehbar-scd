from app.services.tracing import make_trace, redact
from app.schemas import AskResponse, Citation, Passage
from app.config import Settings


def test_redact_masks_common_direct_identifiers():
    assert redact("reach me a.person@example.com or +1 (555) 123-4567") == (
        "reach me [REDACTED_EMAIL] or [REDACTED_PHONE]"
    )


def test_trace_contains_reconstructable_prompt_and_ranked_context():
    settings = Settings(embed_model="test-embed", llm_model="test-llm")
    passage = Passage(chunk_id="c1", text="The rule is 80 percent.", source="policy.pdf",
                      section="1.1", page=2, score=.9, doc_version="2026")
    response = AskResponse(request_id="req1", answer="80 percent", citations=[
        Citation(source="policy.pdf", section="1.1", page=2)], answered_from_context=True,
        confidence="high", retrieved=[], provider="stub")
    row = make_trace(trace_id="req1", question="What is the attendance requirement?",
                     retrieval_query="What is the attendance requirement?", passages=[passage],
                     response=response, settings=settings, index_version="rules-v1",
                     cache_status="MISS", stage_ms={"retrieval": 3.0}, guardrail_actions=[])
    assert row["retrieved"][0]["chunk_id"] == "c1"
    assert row["prompt_sha256"]
    assert "The rule is 80 percent." in row["prompt"][1]["content"]
