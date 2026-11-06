"""The API process. It reads the index; it never builds it (section 4.2).

Run locally with stubs:   make dev     (then open http://localhost:8000)
Run in the container:     uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import os
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .logjson import configure_logging, request_id_var
from .providers.llm import get_provider
from .retrieval import get_retriever
from .routes import ask, health, metrics
from .services.index_state import IndexState
from .services.readiness import (STARTUP_INDEX_TIMEOUT_SECONDS, LazyChromaClient, Readiness,
                                 UnavailableEmbedder, load_embedder)

log = logging.getLogger("rahbar.api")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.settings = settings
    metrics.INDEX_INFO.labels(index_version="unknown", embed_model=settings.embed_model).set(1)

    # Load the pinned embedding model. A failure keeps the pod alive but not ready
    # (/readyz check `embedding_model`); it never crashes the process.
    embedder, embed_error = load_embedder(settings)
    if embed_error:
        log.error("embedding model not loaded", extra={
            "embed_model": settings.embed_model, "cache_dir": settings.embed_cache_dir,
            "error": embed_error})

    # Redis: the semantic cache (D3, ADR 0003) and the turn log (D4, ADR 0005). Short timeouts,
    # because every Redis error only skips the cache or the log; the answer is still returned.
    import redis

    from .services.cache import RedisSemanticCache
    from .services.turns import RedisTurnLog

    redis_client = redis.Redis(host=settings.redis_host, port=settings.redis_port,
                               socket_connect_timeout=0.5, socket_timeout=0.5)
    app.state.cache = RedisSemanticCache(redis_client, settings.cache_threshold,
                                         settings.cache_ttl_seconds, settings.cache_max_entries)
    app.state.turns = RedisTurnLog(redis_client, settings.turn_log_max_entries,
                                   settings.turn_log_ttl_seconds)

    # One lazy Chroma client and one IndexState, shared by retrieval and /readyz. When the
    # active index changes, old-version cache keys are deleted (the keys can no longer match).
    chroma = LazyChromaClient(settings)
    index_state = IndexState(settings, client=chroma,
                             cache_invalidator=app.state.cache.invalidate_except)
    if settings.retriever == "chroma":
        from .retrieval.chroma import ChromaRetriever

        app.state.retriever = ChromaRetriever(
            settings, client=chroma, index_state=index_state,
            embedder=embedder or UnavailableEmbedder(settings.embed_model, embed_error or ""))
    else:
        app.state.retriever = get_retriever(settings)
    app.state.provider = get_provider(settings)

    app.state.readiness = Readiness(
        settings, index_state, embedder, embed_error,
        redis.Redis(host=settings.redis_host, port=settings.redis_port,
                    socket_connect_timeout=1, socket_timeout=1))

    # The embedding pin (section 4.4): check once now and log the result (each dependency
    # call is time-limited, so this adds at most a few seconds). A mismatch is logged at
    # ERROR with both models and both dimensions, and /readyz then answers 503 on every
    # probe. This process only reads the index; the indexer Job writes it.
    result = app.state.readiness.check(index_timeout=STARTUP_INDEX_TIMEOUT_SECONDS)
    log.info("startup readiness", extra=dict(result.body))
    log.info(
        "api started",
        extra={"retriever": settings.retriever, "llm_provider": settings.llm_provider,
               "embed_model": settings.embed_model, "top_k": settings.top_k},
    )
    yield


app = FastAPI(title="RAHBAR API", lifespan=lifespan)


@app.middleware("http")
async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
    candidate = request.headers.get("X-Request-ID", "")
    rid = candidate if _REQUEST_ID.fullmatch(candidate) else uuid.uuid4().hex
    token = request_id_var.set(rid)
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")   # route template, not the raw URL
        elapsed = time.perf_counter() - start
        metrics.REQUESTS.labels(path=path, status=str(status)).inc()
        metrics.LATENCY.labels(path=path).observe(elapsed)
        if path not in ("/healthz", "/readyz", "/metrics"):
            log.info("request", extra={"path": path, "status": status,
                                       "ms": round(elapsed * 1000, 1)})
        request_id_var.reset(token)


app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(ask.router)

# Development only: `make dev` serves the chat UI from this process, so you can try it
# without a cluster. On Kubernetes the ui Deployment serves it and this stays unset.
_ui_dir = os.environ.get("SERVE_UI_DIR")
if _ui_dir:
    app.mount("/", StaticFiles(directory=_ui_dir, html=True), name="ui")
