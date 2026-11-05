"""Readiness checks for /readyz and the embedding-pin check (sections 4.3, 4.4).

The checks run in this order and every one is reported; `failed` names the first failure
(docs/architecture/interfaces.md § HTTP endpoints):

    chroma, index_pointer, collection   from IndexState (the blue/green pointer)
    embedding_pin                       index embed_model/dimension == EMBED_MODEL/loaded model
    embedding_model                     the configured model is loaded in this pod
    redis                               PING answers

A pod that fails any of them is alive but not ready: Kubernetes keeps it out of the Service
instead of restarting it. Each dependency call runs with a short timeout, so a hung Chroma or
Redis makes the probe answer 503 in time, never hang.
"""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any, Protocol

from ..config import Settings
from ..providers.embedding.base import Embedder
from .index_state import IndexState

log = logging.getLogger("rahbar.api")

CHECK_ORDER = ("chroma", "index_pointer", "collection", "embedding_pin", "embedding_model",
               "redis")
INDEX_TIMEOUT_SECONDS = 1.5   # three Chroma calls; the readiness probe gives up after 3 s
# The one check at start-up also imports chromadb and opens the first connection, which
# takes longer than a probe allows; the startup probe gives the pod a minute anyway.
STARTUP_INDEX_TIMEOUT_SECONDS = 10.0
REDIS_TIMEOUT_SECONDS = 1.0


class Pinger(Protocol):
    def ping(self) -> Any: ...


class LazyChromaClient:
    """A Chroma HttpClient that connects on first use, not when it is built.

    chromadb.HttpClient() contacts the server in its constructor and raises if Chroma is down.
    Built at start-up, that would crash the API in a loop instead of reporting "not ready:
    chroma". A failed connection is retried on the next call."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any | None = None

    def _get(self) -> Any:
        if self._client is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            self._client = chromadb.HttpClient(
                host=self._settings.chroma_host, port=self._settings.chroma_port,
                settings=ChromaSettings(anonymized_telemetry=False))
        return self._client

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get(), name)


class UnavailableEmbedder:
    """Stands in when the configured model could not be loaded. The pod stays up and
    /readyz reports `embedding_model`; any retrieval raises instead of answering."""

    dimension = 0

    def __init__(self, model_name: str, error: str) -> None:
        self.model_name = model_name
        self.error = error

    def embed_query(self, text: str) -> list[float]:
        raise RuntimeError(f"embedding model {self.model_name} is not loaded: {self.error}")


def load_embedder(settings: Settings) -> tuple[Embedder | None, str | None]:
    """Load EMBED_MODEL from EMBED_CACHE_DIR. Never raises: a failure is returned as text and
    shown later as the `embedding_model` check (workflows.md § Startup and readiness)."""
    try:
        embedder: Embedder
        if settings.embed_model == "dummy-768":
            from ..providers.embedding.dummy import DummyEmbedder

            embedder = DummyEmbedder()
        else:
            from ..providers.embedding.fastembed import FastEmbedder

            embedder = FastEmbedder(settings.embed_model, settings.embed_cache_dir)
        if not embedder.dimension:          # learn the real vector length once
            embedder.embed_query("dimension probe")
        return embedder, None
    except Exception as exc:  # noqa: BLE001 - any load failure means "not ready", not a crash
        return None, f"{type(exc).__name__}: {exc}"


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    body: dict[str, Any]


class Readiness:
    def __init__(self, settings: Settings, index_state: IndexState, embedder: Embedder | None,
                 embed_error: str | None, redis: Pinger) -> None:
        self.settings = settings
        self.index_state = index_state
        self.embedder = embedder
        self.embed_error = embed_error
        self.redis = redis
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="readyz")
        self._logged_conflict: tuple[Any, ...] | None = None

    def _bounded(self, future: Future[Any], seconds: float) -> Any:
        return future.result(timeout=seconds)

    def check(self, index_timeout: float = INDEX_TIMEOUT_SECONDS) -> ReadinessResult:
        checks: dict[str, str] = {}
        details: dict[str, str] = {}
        active: str | None = None
        metadata: dict[str, Any] = {}

        # 1-3: chroma, index_pointer, collection (re-read on every probe)
        try:
            status = self._bounded(self._pool.submit(self.index_state.refresh), index_timeout)
            checks.update({name: status.checks.get(name, "error")
                           for name in ("chroma", "index_pointer", "collection")})
            details.update(status.details)
            active, metadata = status.active, dict(status.metadata)
        except FutureTimeout:
            checks.update(chroma="timeout", index_pointer="skipped", collection="skipped")
            details["chroma"] = f"no answer within {index_timeout}s"
        except Exception as exc:  # noqa: BLE001
            checks.update(chroma="error", index_pointer="skipped", collection="skipped")
            details["chroma"] = str(exc)

        # 4: embedding_pin, only meaningful once the active collection's metadata is known
        if checks["collection"] == "ok":
            conflict = self._pin_conflict(active or "", metadata)
            if conflict:
                checks["embedding_pin"] = "mismatch"
                details["embedding_pin"] = conflict
            else:
                checks["embedding_pin"] = "ok"
                self._logged_conflict = None
        else:
            checks["embedding_pin"] = "skipped"

        # 5: embedding_model
        if self.embedder is not None and self.embed_error is None:
            checks["embedding_model"] = "ok"
        else:
            checks["embedding_model"] = "error"
            details["embedding_model"] = (f"{self.settings.embed_model} not loaded from "
                                          f"{self.settings.embed_cache_dir}: {self.embed_error}")

        # 6: redis
        try:
            self._bounded(self._pool.submit(self.redis.ping), REDIS_TIMEOUT_SECONDS)
            checks["redis"] = "ok"
        except FutureTimeout:
            checks["redis"] = "timeout"
            details["redis"] = f"no PING answer within {REDIS_TIMEOUT_SECONDS}s"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = "error"
            details["redis"] = str(exc)

        ordered = {name: checks[name] for name in CHECK_ORDER}
        failed = next((name for name, value in ordered.items() if value != "ok"), None)
        body: dict[str, Any] = {"status": "ready" if failed is None else "not_ready",
                                "checks": ordered, "index": active}
        if failed is not None:
            body["failed"] = failed
            body["detail"] = f"{failed}: {details.get(failed, ordered[failed])}"
        return ReadinessResult(failed is None, body)

    def _pin_conflict(self, collection: str, metadata: dict[str, Any]) -> str | None:
        """Compare the index's pin with this pod's configuration. Logs the conflict at ERROR
        the first time it is seen (at start-up, or when an index built with another model is
        activated while the pod runs), with both models and both dimensions."""
        index_model = metadata.get("embed_model")
        index_dimension = metadata.get("dimension")
        configured_dimension = self.embedder.dimension if self.embedder is not None else None
        model_differs = index_model != self.settings.embed_model
        dimension_differs = (configured_dimension is not None and index_dimension is not None
                             and int(index_dimension) != int(configured_dimension))
        if not (model_differs or dimension_differs):
            return None
        conflict = (self.settings.embed_model, index_model, configured_dimension,
                    index_dimension, collection)
        if conflict != self._logged_conflict:
            log.error("embedding pin mismatch", extra={
                "configured_model": self.settings.embed_model, "index_model": index_model,
                "configured_dimension": configured_dimension, "index_dimension": index_dimension,
                "collection": collection})
            self._logged_conflict = conflict
        return (f"configured {self.settings.embed_model} ({configured_dimension} dimensions) but "
                f"index {collection} was built with {index_model} ({index_dimension} dimensions)")
