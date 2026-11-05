"""Token counting with the tokenizer bundled with FastEmbed's pinned model."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Protocol


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class FastEmbedTokenCounter:
    def __init__(self, model_name: str, cache_dir: str) -> None:
        from fastembed import TextEmbedding

        # FastEmbed's lazy mode loads the tokenizer for token_count without loading ONNX.
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir, lazy_load=True)

    def count(self, text: str) -> int:
        return int(self._model.token_count(text))


class WhitespaceTokenCounter:
    """A deterministic stand-in for unit tests; production uses FastEmbedTokenCounter."""

    def count(self, text: str) -> int:
        return len(text.split())


@lru_cache(maxsize=4)
def _load(model_name: str, cache_dir: str) -> FastEmbedTokenCounter:
    return FastEmbedTokenCounter(model_name, cache_dir)


def get_tokenizer(model_name: str | None = None, cache_dir: str | None = None) -> TokenCounter:
    return _load(
        model_name or os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5"),
        cache_dir or os.environ.get("EMBED_CACHE_DIR", "/models"),
    )


def count_tokens(text: str, tokenizer: TokenCounter | None = None) -> int:
    return (tokenizer or get_tokenizer()).count(text)
