"""Runtime configuration, read once from environment variables.

On the cluster these variables come from your ConfigMap and Secret (section 4.1).
Nothing here is baked into the image, so one image runs in every environment.
Add your own keys (relevance floor, cache settings, ...) the same way.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Which implementations to load. "stub" needs no cluster, no model, no network.
    retriever: str = "stub"          # RETRIEVER: stub | chroma
    llm_provider: str = "stub"       # LLM_PROVIDER: stub | ollama-host | ollama-incluster | hosted

    # The embedding pin (section 4.4). The indexer reads the same ConfigMap key.
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_cache_dir: str = "/models"

    # Vector store
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    collection: str = "rahbar"
    index_refresh_seconds: int = 10
    superseded_filter: bool = True

    # Redis: readiness, the semantic cache (D3) and the turn log (D4)
    redis_host: str = "redis"
    redis_port: int = 6379
    cache_threshold: float = 0.96    # cosine at or above this is a hit (chosen in 3A3)
    cache_ttl_seconds: int = 86400
    cache_max_entries: int = 500
    turn_log_max_entries: int = 1000
    turn_log_ttl_seconds: int = 604800

    # Retrieval and generation
    top_k: int = 5
    temperature: float = 0.2
    llm_model: str = "llama3.2:3b"
    ollama_url: str = "http://host.minikube.internal:11434"
    hosted_base_url: str = ""        # e.g. an OpenAI-compatible endpoint
    llm_api_key: str = field(default="", repr=False)   # from the Secret; never log it

    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings(
        retriever=os.environ.get("RETRIEVER", "stub"),
        llm_provider=os.environ.get("LLM_PROVIDER", "stub"),
        embed_model=os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5"),
        embed_cache_dir=os.environ.get("EMBED_CACHE_DIR", "/models"),
        chroma_host=os.environ.get("CHROMA_HOST", "chroma"),
        chroma_port=_int("CHROMA_PORT", 8000),
        collection=os.environ.get("CHROMA_COLLECTION", "rahbar"),
        index_refresh_seconds=_int("INDEX_REFRESH_SECONDS", 10),
        superseded_filter=_bool("SUPERSEDED_FILTER", True),
        redis_host=os.environ.get("REDIS_HOST", "redis"),
        redis_port=_int("REDIS_PORT", 6379),
        cache_threshold=_float("CACHE_THRESHOLD", 0.96),
        cache_ttl_seconds=_int("CACHE_TTL_SECONDS", 86400),
        cache_max_entries=_int("CACHE_MAX_ENTRIES", 500),
        turn_log_max_entries=_int("TURN_LOG_MAX_ENTRIES", 1000),
        turn_log_ttl_seconds=_int("TURN_LOG_TTL_SECONDS", 604800),
        top_k=_int("TOP_K", 5),
        temperature=_float("TEMPERATURE", 0.2),
        llm_model=os.environ.get("LLM_MODEL", "llama3.2:3b"),
        ollama_url=os.environ.get("OLLAMA_URL", "http://host.minikube.internal:11434"),
        hosted_base_url=os.environ.get("HOSTED_BASE_URL", ""),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
