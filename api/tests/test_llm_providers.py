import json

import httpx
import pytest

from app.config import Settings
from app.providers.llm.base import ProviderError
from app.providers.llm.hosted import HostedProvider, strict_json_schema
from app.providers.llm.ollama import OllamaProvider
from app.schemas import Answer


def test_strict_schema_closes_nested_objects_and_requires_nullable_fields() -> None:
    schema = strict_json_schema(Answer.model_json_schema())
    citation = schema["$defs"]["Citation"]

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert citation["additionalProperties"] is False
    assert "page" in citation["required"]


def test_hosted_request_shape_and_completion_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "openai/gpt-oss-20b"
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        assert body["temperature"] == 0.2
        assert body["max_completion_tokens"] == 256
        assert body["reasoning_effort"] == "low"
        output = body["response_format"]["json_schema"]
        assert output["strict"] is True
        assert output["schema"]["additionalProperties"] is False
        return httpx.Response(
            200,
            json={
                "model": "openai/gpt-oss-20b",
                "choices": [{"message": {"content": '{"answer":"ok"}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            },
        )

    settings = Settings(
        hosted_base_url="https://api.groq.com/openai/v1",
        llm_api_key="test-key",
        llm_model="openai/gpt-oss-20b",
        llm_max_tokens=256,
        llm_reasoning_effort="low",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    completion = HostedProvider(settings, client=client).complete(
        [{"role": "user", "content": "hello"}], Answer.model_json_schema(), 0.2
    )

    assert completion.text == '{"answer":"ok"}'
    assert completion.tokens_in == 12
    assert completion.tokens_out == 4


@pytest.mark.parametrize(
    ("status", "kind"),
    [(400, "bad_request"), (401, "auth"), (403, "auth"), (429, "rate_limited"), (503, "server")],
)
def test_hosted_status_errors_are_mapped(status: int, kind: str) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    )
    settings = Settings(llm_api_key="test-key", hosted_base_url="https://llm.test")
    provider = HostedProvider(settings, client)

    with pytest.raises(ProviderError) as raised:
        provider.complete([], Answer.model_json_schema(), 0.2)

    assert raised.value.kind == kind


def test_hosted_error_names_the_providers_code_and_masks_the_org_id() -> None:
    body = {"error": {"code": "rate_limit_exceeded", "message": (
        "Rate limit reached for model `openai/gpt-oss-20b` in organization `org_01abcXYZ` "
        "on tokens per minute (TPM): Limit 8000, Used 7600, Requested 1500.")}}
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(429, json=body, headers={"retry-after": "3"})))
    settings = Settings(llm_api_key="test-key", hosted_base_url="https://llm.test")

    with pytest.raises(ProviderError) as raised:
        HostedProvider(settings, client).complete([], Answer.model_json_schema(), 0.2)

    message = str(raised.value)
    assert raised.value.kind == "rate_limited"
    assert "rate_limit_exceeded" in message and "retry-after 3s" in message
    assert "org_01abcXYZ" not in message and "org_***" in message
    assert "test-key" not in message


@pytest.mark.parametrize(("headers", "message", "expected"), [
    ({"retry-after": "4"}, "", 4.0),
    ({}, "Limit 8000, Used 7600. Please try again in 2.75s. Need more tokens?", 2.75),
    ({}, "Please try again in 850ms.", 0.85),
    ({}, "Rate limit reached.", None),
])
def test_hosted_rate_limit_carries_the_wait_the_provider_asked_for(
    headers: dict[str, str], message: str, expected: float | None
) -> None:
    body = {"error": {"code": "rate_limit_exceeded", "message": message}}
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(429, json=body, headers=headers)))
    settings = Settings(llm_api_key="test-key", hosted_base_url="https://llm.test")

    with pytest.raises(ProviderError) as raised:
        HostedProvider(settings, client).complete([], Answer.model_json_schema(), 0.2)

    assert raised.value.retry_after == expected


def test_hosted_provider_fails_fast_without_a_key() -> None:
    provider = HostedProvider(Settings(hosted_base_url="https://llm.test"))

    with pytest.raises(ProviderError) as raised:
        provider.complete([], Answer.model_json_schema(), 0.2)

    assert raised.value.kind == "not_configured"


def test_ollama_request_shape_and_completion_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://ollama.test:11434/api/chat"
        body = json.loads(request.content)
        assert body["model"] == "llama3.2:3b"
        assert body["stream"] is False
        assert body["options"] == {"temperature": 0.3}
        assert body["format"]["additionalProperties"] is False
        return httpx.Response(
            200,
            json={
                "model": "llama3.2:3b",
                "message": {"content": '{"answer":"ok"}'},
                "prompt_eval_count": 15,
                "eval_count": 6,
            },
        )

    settings = Settings(llm_model="llama3.2:3b", ollama_url="http://ollama.test:11434")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    completion = OllamaProvider(settings, client=client).complete(
        [{"role": "user", "content": "hello"}], Answer.model_json_schema(), 0.3
    )

    assert completion.tokens_in == 15
    assert completion.tokens_out == 6
