from dataclasses import replace

import pytest

from pipeline.config import get_settings
from pipeline.dummy import DUMMY_CHUNKS, DUMMY_DIM, DUMMY_MODEL, fake_vector, write_dummy_index
from pipeline.store import store
from test_starter_dummy import FakeClient


def dummy_vectors():
    return [fake_vector(chunk.text) for chunk in DUMMY_CHUNKS]


def test_store_pointer_moves_only_after_complete() -> None:
    client = FakeClient()
    assert write_dummy_index(get_settings(), client) == len(DUMMY_CHUNKS)
    pointer = client.collections["rahbar-active"]
    active = client.collections[pointer.metadata["active"]]
    assert active.metadata["status"] == "complete"
    assert active.count() == 3


def test_store_failure_leaves_pointer() -> None:
    client = FakeClient()
    settings = replace(get_settings(), embed_model=DUMMY_MODEL)
    write_dummy_index(settings, client)
    pointer = client.collections["rahbar-active"]
    old_active = pointer.metadata["active"]
    client.fail_on_add = True
    with pytest.raises(RuntimeError, match="simulated add failure"):
        store(DUMMY_CHUNKS, dummy_vectors(), settings, client=client)
    assert pointer.metadata["active"] == old_active
    assert client.collections[old_active].metadata["status"] == "complete"


def test_store_prunes_to_two() -> None:
    client = FakeClient()
    settings = replace(get_settings(), embed_model=DUMMY_MODEL, keep_collections=2)
    for _ in range(4):
        store(DUMMY_CHUNKS, dummy_vectors(), settings, client=client)
    versions = [name for name in client.collections if name.startswith("rahbar-v")]
    assert len(versions) == 2
    pointer = client.collections["rahbar-active"]
    assert {pointer.metadata["active"], pointer.metadata["previous"]} == set(versions)


def test_store_writes_pin_metadata() -> None:
    client = FakeClient()
    settings = replace(get_settings(), embed_model=DUMMY_MODEL)
    store(DUMMY_CHUNKS, dummy_vectors(), settings, client=client)
    pointer = client.collections["rahbar-active"]
    metadata = client.collections[pointer.metadata["active"]].metadata
    assert metadata["embed_model"] == DUMMY_MODEL
    assert metadata["dimension"] == DUMMY_DIM
    assert metadata["index_version"] == pointer.metadata["active"]
    assert metadata["document_count"] == len({chunk.source for chunk in DUMMY_CHUNKS})


def test_store_rejects_vector_count_mismatch() -> None:
    with pytest.raises(ValueError, match="chunks but"):
        store(DUMMY_CHUNKS, [], get_settings(), client=FakeClient())
