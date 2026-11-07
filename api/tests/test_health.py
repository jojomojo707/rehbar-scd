"""/healthz, /readyz and the embedding-pin check (sections 4.3, 4.4; task 2A5).

Fakes stand in for Chroma, Redis and the model: no cluster, no model, no network."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.services import readiness as readiness_mod
from app.services.index_state import IndexStatus
from app.services.readiness import (CHECK_ORDER, LazyChromaClient, Readiness, load_embedder)

ACTIVE = "rahbar-v20261105-030000"
INDEX_OK = {"chroma": "ok", "index_pointer": "ok", "collection": "ok"}


# A hung dependency blocks on an Event instead of sleeping for "timeout + a bit": the check
# must give up on its own timeout, and the fixture below releases every hung call afterwards,
# so no test depends on a sleep being long enough.
_HUNG: list[threading.Event] = []
HANG_CAP_SECONDS = 30.0      # never reached; only stops a broken test from hanging CI


def _hang(release: threading.Event | None) -> None:
    if release is not None:
        _HUNG.append(release)
        release.wait(HANG_CAP_SECONDS)


@pytest.fixture(autouse=True)
def _release_hung_calls() -> Iterator[None]:
    yield
    while _HUNG:
        _HUNG.pop().set()


class FakeIndexState:
    def __init__(self, checks: dict[str, str] | None = None, model: str = "dummy-768",
                 dimension: int = 768, error: Exception | None = None,
                 release: threading.Event | None = None):
        self.checks = checks or dict(INDEX_OK)
        self.metadata = {"embed_model": model, "dimension": dimension, "status": "complete"}
        self.error = error
        self.release = release      # set: the call blocks until this Event is set
        self.calls = 0

    def refresh(self) -> IndexStatus:
        self.calls += 1
        _hang(self.release)
        if self.error:
            raise self.error
        failed = next((k for k, v in self.checks.items() if v != "ok"), None)
        details = {failed: f"{failed} is {self.checks[failed]}"} if failed else {}
        return IndexStatus(ACTIVE, None, self.metadata, self.checks, details, failed)


class FakeEmbedder:
    def __init__(self, model_name: str = "dummy-768", dimension: int = 768) -> None:
        self.model_name, self.dimension = model_name, dimension

    def embed_query(self, text: str) -> list[float]:
        return [0.0] * self.dimension


class FakeRedis:
    def __init__(self, error: Exception | None = None,
                 release: threading.Event | None = None) -> None:
        self.error, self.release, self.calls = error, release, 0

    def ping(self) -> bool:
        self.calls += 1
        _hang(self.release)
        if self.error:
            raise self.error
        return True


def make(index: FakeIndexState | None = None, embedder: Any = "default",
         embed_error: str | None = None, redis: FakeRedis | None = None,
         embed_model: str = "dummy-768") -> Readiness:
    settings = Settings(embed_model=embed_model)
    return Readiness(settings, index or FakeIndexState(),  # type: ignore[arg-type]
                     FakeEmbedder() if embedder == "default" else embedder, embed_error,
                     redis or FakeRedis())


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("RETRIEVER", "stub")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_readyz_ready_when_every_check_passes(client: TestClient) -> None:
    client.app.state.readiness = make()  # type: ignore[attr-defined]
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "checks": {name: "ok" for name in CHECK_ORDER},
                        "index": ACTIVE}


def test_healthz_touches_no_dependency(client: TestClient) -> None:
    index, redis = FakeIndexState(), FakeRedis()
    client.app.state.readiness = make(index=index, redis=redis)  # type: ignore[attr-defined]
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "alive"}
    assert index.calls == 0 and redis.calls == 0


@pytest.mark.parametrize(("readiness", "failed", "value"), [
    (lambda: make(index=FakeIndexState(error=ConnectionError("chroma:8000 refused"))),
     "chroma", "error"),
    (lambda: make(index=FakeIndexState(release=threading.Event())),
     "chroma", "timeout"),
    (lambda: make(index=FakeIndexState({**INDEX_OK, "index_pointer": "missing",
                                        "collection": "skipped"})), "index_pointer", "missing"),
    (lambda: make(index=FakeIndexState({**INDEX_OK, "collection": "empty"})),
     "collection", "empty"),
    (lambda: make(index=FakeIndexState({**INDEX_OK, "collection": "incomplete"})),
     "collection", "incomplete"),
    (lambda: make(index=FakeIndexState(model="BAAI/bge-small-en-v1.5", dimension=384)),
     "embedding_pin", "mismatch"),
    (lambda: make(index=FakeIndexState(dimension=384)), "embedding_pin", "mismatch"),
    (lambda: make(embedder=None, embed_error="ValueError: model files missing"),
     "embedding_model", "error"),
    (lambda: make(redis=FakeRedis(error=ConnectionError("redis:6379 refused"))),
     "redis", "error"),
    (lambda: make(redis=FakeRedis(release=threading.Event())),
     "redis", "timeout"),
], ids=["chroma-down", "chroma-hangs", "no-pointer", "empty", "building", "pin-model",
        "pin-dimension", "model-not-loaded", "redis-down", "redis-hangs"])
def test_readyz_reports_each_failure(client: TestClient, readiness: Any, failed: str,
                                     value: str) -> None:
    client.app.state.readiness = readiness()  # type: ignore[attr-defined]
    r = client.get("/readyz")
    body = r.json()
    assert r.status_code == 503
    assert body["status"] == "not_ready"
    assert body["failed"] == failed
    assert body["checks"][failed] == value
    assert list(body["checks"]) == list(CHECK_ORDER)          # every check reported, in order
    assert body["detail"].startswith(f"{failed}: ")


def test_pin_mismatch_logs_conflict_once(caplog: pytest.LogCaptureFixture) -> None:
    readiness = make(index=FakeIndexState(model="dummy-768", dimension=768),
                     embedder=FakeEmbedder("BAAI/bge-small-en-v1.5", 384),
                     embed_model="BAAI/bge-small-en-v1.5")
    with caplog.at_level(logging.ERROR, logger="rahbar.api"):
        first = readiness.check()
        readiness.check()                       # the next probe does not repeat the line
    records = [r for r in caplog.records if r.getMessage() == "embedding pin mismatch"]
    assert len(records) == 1
    fields = records[0].__dict__
    assert (fields["configured_model"], fields["index_model"]) == ("BAAI/bge-small-en-v1.5",
                                                                   "dummy-768")
    assert (fields["configured_dimension"], fields["index_dimension"]) == (384, 768)
    assert fields["collection"] == ACTIVE
    assert first.body["detail"] == (
        f"embedding_pin: configured BAAI/bge-small-en-v1.5 (384 dimensions) but index {ACTIVE} "
        "was built with dummy-768 (768 dimensions)")


def test_startup_check_waits_longer_than_a_probe(caplog: pytest.LogCaptureFixture) -> None:
    """The first check imports chromadb and connects; it must still see the pin conflict."""
    answered = threading.Event()
    slow = FakeIndexState(model="dummy-768", dimension=768, release=answered)
    # Chroma answers after the probe budget but inside the startup budget.
    threading.Timer(readiness_mod.INDEX_TIMEOUT_SECONDS + 0.5, answered.set).start()
    readiness = make(index=slow, embedder=FakeEmbedder("BAAI/bge-small-en-v1.5", 384),
                     embed_model="BAAI/bge-small-en-v1.5")
    with caplog.at_level(logging.ERROR, logger="rahbar.api"):
        result = readiness.check(index_timeout=readiness_mod.STARTUP_INDEX_TIMEOUT_SECONDS)
    assert result.body["failed"] == "embedding_pin"
    assert any(r.getMessage() == "embedding pin mismatch" for r in caplog.records)


def test_lazy_chroma_client_does_not_connect_until_used() -> None:
    lazy = LazyChromaClient(Settings(chroma_host="localhost", chroma_port=1))
    with pytest.raises(Exception):            # noqa: B017 - connection refused, at use time
        lazy.heartbeat()


def test_load_embedder_reports_failure_without_raising() -> None:
    embedder, error = load_embedder(Settings(embed_model="no-such/model",
                                             embed_cache_dir="/nonexistent"))
    assert embedder is None and error


def test_load_embedder_dummy_has_768_dimensions() -> None:
    embedder, error = load_embedder(Settings(embed_model="dummy-768"))
    assert error is None and embedder is not None and embedder.dimension == 768
