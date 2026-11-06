"""Semantic cache on Redis (brief section 3.3; design D3, workflows.md § Semantic cache).

A cache entry is a question vector plus the full AskResponse it produced. A new question is a
hit when the cosine similarity of its vector to a stored one is at or above CACHE_THRESHOLD.

Keys (data-models.md § Redis keyspace):

    rahbar:cache:<index_version>:<fingerprint>:<mode>:idx        sorted set of entry ids
    rahbar:cache:<index_version>:<fingerprint>:<mode>:e:<id>     hash: v, q, resp, ts
    rahbar:cache:version                                         last index version served

The index version (the active collection name) is inside every key, so after a re-index a
lookup can no longer reach an old answer. Deleting the old keys is only clean-up; TTLs back it
up. The fingerprint covers the settings that change an answer, and the mode keeps questions
about older document versions apart from current ones.

Every Redis error is caught here: the request still gets its answer, the cache is skipped, a
WARNING is logged and rahbar_dependency_errors_total{dependency="redis"} goes up.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
import uuid
from array import array
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from ..routes import metrics
from ..schemas import AskResponse

log = logging.getLogger("rahbar.cache")

PREFIX = "rahbar:cache"
VERSION_KEY = f"{PREFIX}:version"


@dataclass(frozen=True)
class CacheHit:
    response: AskResponse
    score: float


class SemanticCache(Protocol):
    def lookup(self, namespace: str, vector: list[float]) -> CacheHit | None: ...

    def store(
        self, namespace: str, vector: list[float], question: str, response: AskResponse
    ) -> None: ...

    def invalidate_except(self, index_version: str) -> int: ...


class NullSemanticCache:
    """Disabled cache: the stub retriever has no index version and no vectors."""

    def lookup(self, namespace: str, vector: list[float]) -> CacheHit | None:
        return None

    def store(
        self, namespace: str, vector: list[float], question: str, response: AskResponse
    ) -> None:
        return None

    def invalidate_except(self, index_version: str) -> int:
        return 0


def config_fingerprint(parts: Mapping[str, object]) -> str:
    """First 8 hex characters of a SHA-256 over the settings that change an answer.

    The caller passes PROMPT_VERSION, LLM_MODEL, TEMPERATURE, TOP_K, RELEVANCE_FLOOR,
    HYBRID_RETRIEVAL and SUPERSEDED_FILTER. Changing any of them starts a fresh namespace.
    """
    text = "|".join(f"{key}={parts[key]}" for key in sorted(parts))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def cache_namespace(index_version: str, fingerprint: str, include_superseded: bool) -> str:
    """`cur` for current documents only, `all` when the user asked about an older version."""
    mode = "all" if include_superseded else "cur"
    return f"{PREFIX}:{index_version}:{fingerprint}:{mode}"


def is_cacheable(
    *,
    follow_up: bool,
    outcome: str,
    answered_from_context: bool,
    citations: int,
    dropped_citations: int,
) -> bool:
    """validation-and-errors.md § Cacheability: all four conditions must hold.

    (The fifth, "Redis is reachable", is checked by `store` itself.) So follow-ups,
    abstentions (floor, model or out-of-scope), fallbacks, cache hits, and answers that had
    a citation or inline marker removed are never stored.
    """
    return (
        not follow_up
        and outcome == "answered"
        and answered_from_context
        and citations > 0
        and dropped_citations == 0
    )


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return list(vector)
    return [value / norm for value in vector]


def _pack(vector: list[float]) -> bytes:
    return array("f", vector).tobytes()


def _unpack(raw: bytes) -> list[float]:
    values = array("f")
    values.frombytes(raw)
    return values.tolist()


class RedisSemanticCache:
    """Brute-force cosine search over at most CACHE_MAX_ENTRIES vectors per namespace."""

    def __init__(
        self,
        client: Any,
        threshold: float,
        ttl_seconds: int,
        max_entries: int,
    ) -> None:
        self.client = client
        self.threshold = threshold
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.max_entries = max(1, int(max_entries))

    def lookup(self, namespace: str, vector: list[float]) -> CacheHit | None:
        if not vector:
            return None
        try:
            ids = [_text(value) for value in self.client.zrange(f"{namespace}:idx", 0, -1)]
            if not ids:
                return None
            pipe = self.client.pipeline(transaction=False)
            for entry_id in ids:
                pipe.hget(f"{namespace}:e:{entry_id}", "v")
            stored_vectors = pipe.execute()

            query = _unit(vector)
            best_id, best_score = None, -1.0
            for entry_id, raw in zip(ids, stored_vectors):
                if not raw:
                    continue                     # expired or trimmed entry
                stored = _unpack(raw)
                if len(stored) != len(query):
                    continue
                score = sum(a * b for a, b in zip(query, stored))
                if score > best_score:
                    best_id, best_score = entry_id, score
            if best_id is None or best_score < self.threshold:
                return None

            raw_response = self.client.hget(f"{namespace}:e:{best_id}", "resp")
            if not raw_response:
                return None
            # Stored without request_id; the caller sets the current one and cached=True.
            stored_body = json.loads(raw_response)
            response = AskResponse.model_validate({**stored_body, "request_id": ""})
            return CacheHit(response=response, score=best_score)
        except Exception as exc:  # noqa: BLE001 - any Redis or decode failure means "miss"
            _redis_warning("cache lookup", exc)
            return None

    def store(
        self, namespace: str, vector: list[float], question: str, response: AskResponse
    ) -> None:
        if not vector:
            return
        entry_id = uuid.uuid4().hex[:16]
        index_key = f"{namespace}:idx"
        entry_key = f"{namespace}:e:{entry_id}"
        now = time.time()
        # The request_id belongs to the request that produced the answer, not to later hits.
        body = response.model_dump_json(exclude={"request_id"})
        try:
            pipe = self.client.pipeline(transaction=True)
            pipe.hset(entry_key, mapping={
                "v": _pack(_unit(vector)), "q": question, "resp": body, "ts": str(now)})
            pipe.expire(entry_key, self.ttl_seconds)
            pipe.zadd(index_key, {entry_id: now})
            pipe.expire(index_key, self.ttl_seconds)
            pipe.execute()

            # Keep the newest max_entries; delete the trimmed entries' hashes as well.
            overflow = [_text(value) for value in
                        self.client.zrange(index_key, 0, -(self.max_entries + 1))]
            if overflow:
                pipe = self.client.pipeline(transaction=True)
                pipe.zrem(index_key, *overflow)
                pipe.unlink(*[f"{namespace}:e:{old}" for old in overflow])
                pipe.execute()
        except Exception as exc:  # noqa: BLE001
            _redis_warning("cache store", exc)

    def invalidate_except(self, index_version: str) -> int:
        """Delete every cache key that does not belong to `index_version`.

        Called when this pod sees the active pointer name a new collection (and once at
        start-up). Several pods may do it at once; deleting a key twice is harmless.
        """
        try:
            if _text(self.client.get(VERSION_KEY) or b"") == index_version:
                return 0
            self.client.set(VERSION_KEY, index_version)
            keep = f"{PREFIX}:{index_version}:"
            deleted = 0
            batch: list[str] = []
            for key in self.client.scan_iter(match=f"{PREFIX}:*", count=500):
                name = _text(key)
                if name == VERSION_KEY or name.startswith(keep):
                    continue
                batch.append(name)
                if len(batch) >= 500:
                    deleted += int(self.client.unlink(*batch))
                    batch = []
            if batch:
                deleted += int(self.client.unlink(*batch))
            log.info("cache invalidated", extra={"index_version": index_version,
                                                 "deleted_keys": deleted})
            return deleted
        except Exception as exc:  # noqa: BLE001
            _redis_warning("cache invalidation", exc)
            return 0


def _text(value: bytes | str) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _redis_warning(operation: str, exc: Exception) -> None:
    metrics.DEPENDENCY_ERRORS.labels(dependency="redis").inc()
    log.warning(f"{operation} skipped: redis error",
                extra={"error_type": type(exc).__name__, "error": str(exc)})
