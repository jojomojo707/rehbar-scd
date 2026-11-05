from app.config import Settings
from app.providers.embedding.dummy import DummyEmbedder
from app.retrieval.base import RetrievalQuery
from app.retrieval.chroma import ChromaRetriever
from app.services.index_state import IndexStatus


class FakeCollection:
    def __init__(self) -> None:
        self.kwargs = None

    def query(self, **kwargs):
        self.kwargs = kwargs
        return {
            "ids": [["new", "old"]],
            "documents": [["current rule", "August 2023 rule"]],
            "metadatas": [[
                {"source": "current.pdf", "section": "1", "page": 1,
                 "doc_version": "2026", "superseded": False},
                {"source": "old.pdf", "section": "1", "page": 2,
                 "doc_version": "August 2023", "superseded": True},
            ]],
            "distances": [[0.1, 0.2]],
        }


class FakeClient:
    def __init__(self) -> None:
        self.collection = FakeCollection()
        self.name = None

    def get_collection(self, *, name, embedding_function):
        assert embedding_function is None
        self.name = name
        return self.collection


class FakeIndexState:
    def current(self):
        return IndexStatus(active="rahbar-v1", previous=None,
                           metadata={"embed_model": "dummy-768",
                                     "superseded_versions": "2023-08"},
                           checks={"collection": "ok"})


def test_retriever_excludes_superseded_and_converts_distance() -> None:
    client = FakeClient()
    settings = Settings(embed_model="dummy-768")
    retriever = ChromaRetriever(settings, client, DummyEmbedder(), FakeIndexState())
    query = RetrievalQuery("current rule", [0.0] * 768, 2)
    results = retriever.retrieve(query)
    assert client.name == "rahbar-v1"
    assert client.collection.kwargs["where"] == {"superseded": False}
    assert [item.chunk_id for item in results] == ["new"]
    assert results[0].score == 0.9


def test_explicit_year_returns_matching_superseded_version() -> None:
    client = FakeClient()
    settings = Settings(embed_model="dummy-768")
    retriever = ChromaRetriever(settings, client, DummyEmbedder(), FakeIndexState())
    query = RetrievalQuery("August 2023 policy", [0.0] * 768, 1,
                           include_superseded=True, requested_year="2023")
    results = retriever.retrieve(query)
    assert client.collection.kwargs["where"] is None
    assert len(results) == 1 and results[0].chunk_id == "old"


def test_v01_question_enables_superseded_search_from_index_metadata() -> None:
    client = FakeClient()
    retriever = ChromaRetriever(
        Settings(embed_model="dummy-768"), client, DummyEmbedder(), FakeIndexState()
    )
    results = retriever.retrieve(
        "Under clause 1.17 of the August 2023 rules, how is the normal semester course load determined?"
    )
    assert client.collection.kwargs["where"] is None
    assert [item.chunk_id for item in results] == ["old"]


def test_v02_current_year_question_keeps_superseded_filter_enabled() -> None:
    client = FakeClient()
    retriever = ChromaRetriever(
        Settings(embed_model="dummy-768"), client, DummyEmbedder(), FakeIndexState()
    )
    results = retriever.retrieve("What do the June 2026 rules say?")
    assert client.collection.kwargs["where"] == {"superseded": False}
    assert [item.chunk_id for item in results] == ["new"]


def test_superseded_filter_can_be_disabled_by_config() -> None:
    client = FakeClient()
    settings = Settings(embed_model="dummy-768", superseded_filter=False)
    retriever = ChromaRetriever(settings, client, DummyEmbedder(), FakeIndexState())
    results = retriever.retrieve(RetrievalQuery("all versions", [0.0] * 768, 2))
    assert client.collection.kwargs["where"] is None
    assert [item.chunk_id for item in results] == ["new", "old"]
