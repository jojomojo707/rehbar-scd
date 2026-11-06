"""Semantic cache and turn log (3A1). fakeredis is an in-memory Redis, so no server is needed."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import fakeredis
import pytest
import redis

from app.config import Settings
from app.schemas import AskResponse, Citation, RetrievedRef
from app.services.cache import (
    VERSION_KEY,
    RedisSemanticCache,
    cache_namespace,
    config_fingerprint,
    is_cacheable,
)
from app.services.index_state import IndexState
from app.services.turns import TURNS_KEY, RedisTurnLog, Turn

NS = cache_namespace("rahbar-v1", "abcd1234", include_superseded=False)


def response(answer: str = "80% [rules.pdf / 1.22]", request_id: str = "req-1") -> AskResponse:
    return AskResponse(
        request_id=request_id,
        answer=answer,
        citations=[Citation(source="rules.pdf", section="1.22", page=4)],
        answered_from_context=True,
        confidence="high",
        retrieved=[RetrievedRef(chunk_id="c1", source="rules.pdf", section="1.22", page=4,
                                score=0.81)],
        provider="stub",
    )


@pytest.fixture
def client() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


def make_cache(client: Any, threshold: float = 0.6, max_entries: int = 500) -> RedisSemanticCache:
    return RedisSemanticCache(client, threshold=threshold, ttl_seconds=60, max_entries=max_entries)


def test_cache_hit_at_threshold(client: fakeredis.FakeRedis) -> None:
    cache = make_cache(client, threshold=0.6)
    cache.store(NS, [1.0, 0.0], "What is the minimum attendance?", response())
    # [3, 4] normalised is [0.6, 0.8]: cosine with [1, 0] is exactly 0.6, the threshold.
    hit = cache.lookup(NS, [3.0, 4.0])
    assert hit is not None
    assert hit.score == pytest.approx(0.6)
    assert hit.response.answer == "80% [rules.pdf / 1.22]"
    assert hit.response.retrieved[0].chunk_id == "c1"   # citations and retrieved stay together
    assert hit.response.request_id == ""                # the old request's id is not reused


def test_cache_miss_below_threshold(client: fakeredis.FakeRedis) -> None:
    cache = make_cache(client, threshold=0.6)
    cache.store(NS, [1.0, 0.0], "What is the minimum attendance?", response())
    assert cache.lookup(NS, [3.0, 4.01]) is None        # cosine just under 0.6


def test_lookup_picks_the_closest_entry(client: fakeredis.FakeRedis) -> None:
    cache = make_cache(client, threshold=0.5)
    cache.store(NS, [1.0, 0.0], "a", response("far [rules.pdf / 1.22]"))
    cache.store(NS, [0.0, 1.0], "b", response("near [rules.pdf / 1.22]"))
    hit = cache.lookup(NS, [0.1, 1.0])
    assert hit is not None and hit.response.answer.startswith("near")


def test_namespaces_do_not_share_entries(client: fakeredis.FakeRedis) -> None:
    cache = make_cache(client, threshold=0.5)
    cache.store(NS, [1.0, 0.0], "q", response())
    older_versions = cache_namespace("rahbar-v1", "abcd1234", include_superseded=True)
    other_settings = cache_namespace("rahbar-v1", "ffff0000", include_superseded=False)
    other_index = cache_namespace("rahbar-v2", "abcd1234", include_superseded=False)
    for namespace in (older_versions, other_settings, other_index):
        assert cache.lookup(namespace, [1.0, 0.0]) is None


def test_namespace_and_fingerprint_shape() -> None:
    parts = {"PROMPT_VERSION": "1", "LLM_MODEL": "m", "TEMPERATURE": 0.2, "TOP_K": 5,
             "RELEVANCE_FLOOR": 0.6, "HYBRID_RETRIEVAL": False, "SUPERSEDED_FILTER": True}
    fingerprint = config_fingerprint(parts)
    assert len(fingerprint) == 8
    assert config_fingerprint(dict(reversed(list(parts.items())))) == fingerprint
    assert config_fingerprint({**parts, "TOP_K": 3}) != fingerprint
    assert cache_namespace("rahbar-v1", fingerprint, False).endswith(f"{fingerprint}:cur")
    assert cache_namespace("rahbar-v1", fingerprint, True).endswith(f"{fingerprint}:all")


@pytest.mark.parametrize(
    ("case", "follow_up", "outcome", "from_context", "citations", "dropped"),
    [
        ("follow-up", True, "answered", True, 1, 0),
        ("floor or model abstention", False, "abstained", False, 0, 0),
        ("out of scope", False, "abstained", False, 0, 0),
        ("fallback", False, "fallback", False, 0, 0),
        ("already a cache hit", False, "cached", True, 1, 0),
        ("no citation left", False, "answered", True, 0, 0),
        ("a citation was dropped", False, "answered", True, 1, 1),
    ],
)
def test_never_cached(case: str, follow_up: bool, outcome: str, from_context: bool,
                      citations: int, dropped: int) -> None:
    assert not is_cacheable(follow_up=follow_up, outcome=outcome,
                            answered_from_context=from_context, citations=citations,
                            dropped_citations=dropped), case


def test_validated_answer_is_cacheable() -> None:
    assert is_cacheable(follow_up=False, outcome="answered", answered_from_context=True,
                        citations=1, dropped_citations=0)


def test_cache_invalidated_on_index_change(client: fakeredis.FakeRedis) -> None:
    cache = make_cache(client, threshold=0.5)
    assert cache.invalidate_except("rahbar-v1") == 0     # first version seen: nothing to delete
    cache.store(NS, [1.0, 0.0], "q", response())
    assert cache.lookup(NS, [1.0, 0.0]) is not None

    deleted = cache.invalidate_except("rahbar-v2")
    assert deleted == 2                                  # the idx set and the entry hash
    assert client.get(VERSION_KEY) == b"rahbar-v2"
    assert cache.lookup(NS, [1.0, 0.0]) is None
    assert cache.invalidate_except("rahbar-v2") == 0     # a second pod: no work, no error


def test_entries_are_trimmed_to_max(client: fakeredis.FakeRedis) -> None:
    cache = make_cache(client, threshold=0.5, max_entries=2)
    for x in (1.0, 2.0, 3.0):
        cache.store(NS, [x, 1.0], f"q{x}", response())
    assert client.zcard(f"{NS}:idx") == 2
    assert len(list(client.scan_iter(match=f"{NS}:e:*"))) == 2


def test_every_key_has_a_ttl(client: fakeredis.FakeRedis) -> None:
    cache = make_cache(client)
    cache.store(NS, [1.0, 0.0], "q", response())
    RedisTurnLog(client, max_entries=10, ttl_seconds=60).append(Turn(question="q", answer="a"))
    for key in client.scan_iter(match="rahbar:*"):
        assert client.ttl(key) > 0, key


def test_stored_answer_has_no_request_id(client: fakeredis.FakeRedis) -> None:
    make_cache(client).store(NS, [1.0, 0.0], "q", response(request_id="secret-ish"))
    (entry_key,) = list(client.scan_iter(match=f"{NS}:e:*"))
    assert "request_id" not in json.loads(client.hget(entry_key, "resp"))


class BrokenRedis:
    """Every command fails as if Redis were down."""

    def __getattr__(self, name: str) -> Any:
        def fail(*args: Any, **kwargs: Any) -> Any:
            raise redis.ConnectionError("redis is down")
        return fail


def test_redis_errors_never_reach_the_caller(caplog: pytest.LogCaptureFixture) -> None:
    cache = make_cache(BrokenRedis())
    assert cache.lookup(NS, [1.0, 0.0]) is None
    cache.store(NS, [1.0, 0.0], "q", response())
    assert cache.invalidate_except("rahbar-v2") == 0
    RedisTurnLog(BrokenRedis(), max_entries=10, ttl_seconds=60).append(
        Turn(question="q", answer="a"))
    assert sum("redis error" in record.getMessage() for record in caplog.records) == 4


def test_turn_logged(client: fakeredis.FakeRedis) -> None:
    turns = RedisTurnLog(client, max_entries=2, ttl_seconds=60)
    for i in range(3):
        turns.append(Turn(question=f"q{i}", answer=f"a{i}", request_id=f"r{i}",
                          outcome="cached" if i == 2 else "answered", follow_up=i == 1,
                          history_turns=i))
    stored = [json.loads(item) for item in client.lrange(TURNS_KEY, 0, -1)]
    assert [turn["question"] for turn in stored] == ["q1", "q2"]   # trimmed to the newest 2
    assert stored[-1]["outcome"] == "cached"
    assert set(stored[0]) == {"request_id", "ts", "question", "answer", "answered_from_context",
                              "outcome", "follow_up", "history_turns"}


class FakeChroma:
    """Just enough of the Chroma client for IndexState: a pointer and its collection."""

    def __init__(self, active: str) -> None:
        self.active = active

    def heartbeat(self) -> int:
        return 1

    def get_collection(self, name: str, embedding_function: Any = None) -> Any:
        if name.endswith("-active"):
            return SimpleNamespace(metadata={"active": self.active})
        return SimpleNamespace(metadata={"status": "complete"}, count=lambda: 3)


def test_index_state_invalidates_on_first_sight_and_on_change() -> None:
    seen: list[str] = []
    chroma = FakeChroma("rahbar-v1")
    state = IndexState(Settings(), client=chroma,
                       cache_invalidator=lambda version: seen.append(version) or 0)
    state.refresh()
    state.refresh()                       # same version: not called again
    chroma.active = "rahbar-v2"
    state.refresh()
    assert seen == ["rahbar-v1", "rahbar-v2"]


def test_index_state_survives_a_failing_invalidator() -> None:
    def broken(version: str) -> int:
        raise RuntimeError("boom")

    status = IndexState(Settings(), client=FakeChroma("rahbar-v1"),
                        cache_invalidator=broken).refresh()
    assert status.ready
