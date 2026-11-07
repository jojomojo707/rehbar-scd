"""OpenAI-compatible hosted provider, configured for Groq in the project deployment."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

import httpx

from ...config import Settings
from .base import Completion, ProviderError

_ORG_ID = re.compile(r"\borg_[A-Za-z0-9]+")


def strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Close every object and require every property for constrained JSON output."""
    result = deepcopy(schema)

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object" or "properties" in value:
                properties = value.get("properties", {})
                if isinstance(properties, dict):
                    value["required"] = list(properties)
                value["additionalProperties"] = False
            value.pop("default", None)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(result)
    return result


class HostedProvider:
    name = "hosted"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.Client(timeout=settings.llm_timeout_seconds)

    def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any], temperature: float
    ) -> Completion:
        if not self.settings.llm_api_key:
            raise ProviderError("not_configured", "The hosted provider has no API key.")
        base_url = self.settings.hosted_base_url.rstrip("/")
        if not base_url:
            raise ProviderError("not_configured", "The hosted provider has no base URL.")

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "answer",
                "strict": True,
                "schema": strict_json_schema(schema),
            },
        }
        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": self.settings.llm_max_tokens,
            "reasoning_effort": self.settings.llm_reasoning_effort,
            "response_format": response_format,
        }
        try:
            response = self._client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout", "Hosted generation timed out.") from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                "server", "Hosted generation could not reach its endpoint."
            ) from exc

        if response.status_code >= 400:
            raise _provider_error(response.status_code, _error_detail(response))
        try:
            body = response.json()
            choice = body["choices"][0]
            content = choice["message"]["content"]
            usage = body.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("bad_request", "Hosted response had an invalid shape.") from exc
        if not isinstance(content, str):
            raise ProviderError("bad_request", "Hosted response did not contain text output.")
        return Completion(
            text=content,
            tokens_in=_int_or_zero(usage.get("prompt_tokens")),
            tokens_out=_int_or_zero(usage.get("completion_tokens")),
            model=str(body.get("model") or self.settings.llm_model),
        )


def _error_detail(response: httpx.Response) -> str:
    """The provider's own error code and message (Groq: `rate_limit_exceeded`,
    `json_validate_failed`, ...), so a fallback in the logs says why. The organisation id that
    Groq puts in rate-limit messages is masked; the request never echoes the API key."""
    try:
        error = response.json().get("error") or {}
        code, message = str(error.get("code") or error.get("type") or ""), str(
            error.get("message") or "")
    except (ValueError, AttributeError):
        code, message = "", ""
    message = _ORG_ID.sub("org_***", " ".join(message.split()))[:200]
    retry_after = response.headers.get("retry-after")
    parts = [part for part in (code, message) if part]
    if retry_after:
        parts.append(f"retry-after {retry_after}s")
    return "; ".join(parts)


def _provider_error(status_code: int, detail: str = "") -> ProviderError:
    suffix = f": {detail}" if detail else ""
    if status_code in (401, 403):
        return ProviderError("auth", f"Hosted provider rejected credentials ({status_code}).")
    if status_code == 429:
        return ProviderError("rate_limited", f"Hosted provider rate limit reached{suffix}")
    if status_code >= 500:
        return ProviderError("server", f"Hosted provider returned {status_code}{suffix}")
    return ProviderError("bad_request",
                         f"Hosted provider rejected the request ({status_code}){suffix}")


def _int_or_zero(value: Any) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0
