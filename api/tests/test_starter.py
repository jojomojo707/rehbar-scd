"""Starter tests: they pin down the contract the UI and eval script rely on.

They run with the stub retriever and stub provider: no cluster, no model, no
network. Keep them passing, and add your own next to them (section 6).
"""

from __future__ import annotations

import json
import logging
import re

import pytest
from fastapi.testclient import TestClient

from app.logjson import JsonFormatter, request_id_var


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RETRIEVER", "stub")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_liveness_answers_without_dependencies(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "alive"}


def test_ask_returns_the_response_contract(client: TestClient) -> None:
    from app.schemas import AskResponse

    r = client.post("/api/ask", json={"question": "What is the attendance requirement?"})
    assert r.status_code == 200
    body = AskResponse(**r.json())          # raises if any field is missing or mistyped
    assert body.provider == "stub"
    assert len(body.retrieved) == 3


def test_every_citation_names_a_retrieved_passage(client: TestClient) -> None:
    r = client.post("/api/ask", json={"question": "What does the stub say?"}).json()
    retrieved = {(p["source"], p["section"]) for p in r["retrieved"]}
    assert r["citations"]
    for c in r["citations"]:
        assert (c["source"], c["section"]) in retrieved


def test_request_id_is_echoed(client: TestClient) -> None:
    r = client.post("/api/ask", json={"question": "Echo my id please"},
                    headers={"X-Request-ID": "test-123"})
    assert r.headers["X-Request-ID"] == "test-123"
    assert r.json()["request_id"] == "test-123"


def test_bad_request_id_is_replaced(client: TestClient) -> None:
    r = client.post(
        "/api/ask",
        json={"question": "Replace the invalid request id"},
        headers={"X-Request-ID": "bad id/with spaces"},
    )
    request_id = r.headers["X-Request-ID"]

    assert request_id != "bad id/with spaces"
    assert re.fullmatch(r"[A-Za-z0-9._-]{1,64}", request_id)
    assert r.json()["request_id"] == request_id


def test_request_log_line_has_safe_observability_fields(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import answer as answer_service

    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        answer_service.log,
        "info",
        lambda message, extra: captured.append(extra),
    )
    raw_question = "What does the rule say?"
    response = client.post("/api/ask", json={"question": raw_question})
    request_id = response.json()["request_id"]
    fields = captured[-1]

    assert {
        "top_k",
        "chunk_ids",
        "scores",
        "abstained",
        "question_sha256",
        "question_chars",
        "tokens_in",
        "tokens_out",
    } <= fields.keys()
    assert "question" not in fields
    assert "reasoning" not in fields

    record = logging.LogRecord("rahbar.answer", logging.INFO, __file__, 1, "answered", (), None)
    for key, value in fields.items():
        setattr(record, key, value)
    token = request_id_var.set(request_id)
    try:
        line = JsonFormatter().format(record)
    finally:
        request_id_var.reset(token)
    payload = json.loads(line)

    assert payload["request_id"] == request_id
    assert payload["top_k"] == 5
    assert payload["abstained"] is False
    assert raw_question not in line


@pytest.mark.parametrize("question", ["hi", "x" * 501])
def test_question_length_is_enforced(client: TestClient, question: str) -> None:
    r = client.post("/api/ask", json={"question": question})
    assert r.status_code == 422


def test_metrics_count_requests_by_route(client: TestClient) -> None:
    client.post("/api/ask", json={"question": "Count this request"})
    text = client.get("/metrics").text
    assert 'rahbar_requests_total{path="/api/ask",status="200"}' in text


def test_metrics_expose_day_two_pipeline_instruments(client: TestClient) -> None:
    client.post("/api/ask", json={"question": "Count pipeline metrics"})
    text = client.get("/metrics").text
    for name in (
        "rahbar_retrieval_seconds",
        "rahbar_generation_seconds",
        "rahbar_embedding_seconds",
        "rahbar_cache_lookups_total",
        "rahbar_cache_hit_ratio",
        "rahbar_abstentions_total",
        "rahbar_fallbacks_total",
        "rahbar_llm_tokens_total",
        "rahbar_llm_tokens_per_request",
        "rahbar_citations_dropped_total",
        "rahbar_dependency_errors_total",
        "rahbar_inflight_requests",
        "rahbar_index_info",
    ):
        assert name in text


def test_ask_accepts_bounded_conversation_history(client: TestClient) -> None:
    response = client.post("/api/ask", json={
        "question": "What about the next semester?",
        "history": [{"question": "What is the rule?", "answer": "The rule is stated."}],
    })
    assert response.status_code == 200
    assert response.json()["cached"] is False
