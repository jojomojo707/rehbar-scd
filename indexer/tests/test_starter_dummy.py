"""Starter tests for the week-1 dummy index. No Chroma server needed: a fake
client records what the indexer would have written."""

from __future__ import annotations

import math
from pathlib import Path

from pipeline.config import get_settings
from pipeline.dummy import DUMMY_DIM, DUMMY_MODEL, fake_vector, write_dummy_index
from pipeline.run import discover


class FakeCollection:
    def __init__(self, name: str, metadata: dict) -> None:
        self.name, self.metadata, self.rows = name, metadata, {}
        self.fail_on_add = False

    def add(self, ids, documents, embeddings, metadatas) -> None:
        if self.fail_on_add:
            raise RuntimeError("simulated add failure")
        for i, d, e, m in zip(ids, documents, embeddings, metadatas):
            self.rows[i] = (d, e, m)

    def count(self) -> int:
        return len(self.rows)

    def modify(self, metadata) -> None:
        # Same rule as chromadb-client 1.0.12 (CollectionCommon): the distance function is
        # fixed at creation, and modify() refuses any metadata that still carries hnsw:space.
        if "hnsw:space" in metadata:
            raise ValueError("Changing the distance function of a collection once it is "
                             "created is not supported currently.")
        self.metadata = metadata


class FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    @property
    def fail_on_add(self) -> bool:
        return any(collection.fail_on_add for collection in self.collections.values())

    @fail_on_add.setter
    def fail_on_add(self, value: bool) -> None:
        for collection in self.collections.values():
            collection.fail_on_add = value

    def delete_collection(self, name: str) -> None:
        if name not in self.collections:
            raise ValueError("no such collection")
        del self.collections[name]

    def list_collections(self):
        return list(self.collections)

    def get_collection(self, name: str, embedding_function=None) -> FakeCollection:
        if name not in self.collections:
            raise ValueError("no such collection")
        return self.collections[name]

    def create_collection(self, name: str, metadata: dict, embedding_function=None) -> FakeCollection:
        if name.endswith("-active"):
            active = metadata["active"]
            assert self.collections[active].metadata["status"] == "complete"
        self.collections[name] = FakeCollection(name, metadata)
        self.collections[name].fail_on_add = self.fail_on_add
        return self.collections[name]


def test_dummy_index_writes_three_chunks_and_records_the_model() -> None:
    client = FakeClient()
    assert write_dummy_index(get_settings(), client) == 3
    pointer = client.collections["rahbar-active"]
    col = client.collections[pointer.metadata["active"]]
    assert col.metadata["embed_model"] == DUMMY_MODEL
    assert col.metadata["dimension"] == DUMMY_DIM
    assert col.metadata["status"] == "complete"
    for _doc, vector, meta in col.rows.values():
        assert len(vector) == DUMMY_DIM
        assert set(meta) == {"source", "section", "page", "doc_version", "superseded"}


def test_dummy_index_can_run_twice() -> None:
    client = FakeClient()
    write_dummy_index(get_settings(), client)
    assert write_dummy_index(get_settings(), client) == 3
    pointer = client.collections["rahbar-active"]
    assert pointer.metadata["active"] != pointer.metadata["previous"]
    assert len([n for n in client.collections if n.startswith("rahbar-v")]) == 2


def test_fake_vectors_are_deterministic_unit_vectors() -> None:
    a, b = fake_vector("same text"), fake_vector("same text")
    assert a == b
    assert math.isclose(sum(v * v for v in a), 1.0, rel_tol=1e-9)


def test_discover_reads_fixture_front_matter() -> None:
    fixtures = Path(__file__).resolve().parents[2] / "eval" / "fixtures"
    found = {p.name: (version, old) for p, version, old in discover(str(fixtures))}
    assert found["academic-rules-2023.md"] == ("2023", True)
    assert found["academic-rules-2026.md"] == ("2026", False)
