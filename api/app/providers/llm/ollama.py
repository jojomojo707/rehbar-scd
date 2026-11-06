"""Thin Ollama chat provider; the project documents it but deploys hosted mode."""

from __future__ import annotations

from typing import Any

import httpx

from ...config import Settings
from .base import Completion, ProviderError
from .hosted import strict_json_schema


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.Client(timeout=settings.llm_timeout_seconds)

    def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any], temperature: float
    ) -> Completion:
        url = f"{self.settings.ollama_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "format": strict_json_schema(schema),
            "stream": False,
            "options": {"temperature": temperature},
        }
        try:
            response = self._client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout", "Ollama generation timed out.") from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                "server", "Ollama generation could not reach its endpoint."
            ) from exc

        if response.status_code >= 400:
            if response.status_code in (401, 403):
                kind = "auth"
            elif response.status_code == 429:
                kind = "rate_limited"
            elif response.status_code >= 500:
                kind = "server"
            else:
                kind = "bad_request"
            raise ProviderError(kind, f"Ollama returned {response.status_code}.")
        try:
            body = response.json()
            message = body["message"]
            content = message["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError("bad_request", "Ollama response had an invalid shape.") from exc
        if not isinstance(content, str):
            raise ProviderError("bad_request", "Ollama response did not contain text output.")
        return Completion(
            text=content,
            tokens_in=_int_or_zero(body.get("prompt_eval_count")),
            tokens_out=_int_or_zero(body.get("eval_count")),
            model=str(body.get("model") or self.settings.llm_model),
        )


def _int_or_zero(value: Any) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0
