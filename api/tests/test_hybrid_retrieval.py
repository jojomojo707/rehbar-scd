from app.config import Settings
from app.providers.embedding.dummy import DummyEmbedder
from app.retrieval.base import RetrievalQuery
from app.retrieval.chroma import ChromaRetriever
from app.retrieval.fusion import reciprocal_rank_fusion
from app.schemas import Passage
from app.services.index_state import IndexStatus


def make_passage(chunk_id: str, score: float) -> Passage:
    return Passage(
        chunk_id=chunk_id,
        text=f"text for {chunk_id}",
        source="rules.pdf",
        section="1.17",
        page=1,
        score=score,
    )


def test_rrf_promotes_exact_term_hit() -> None:
    dense = [make_passage("dense-first", 0.9), make_passage("exact-hit", 0.7)]
    exact = [make_passage("exact-hit", 0.7)]

    fused = reciprocal_rank_fusion([dense, exact], top_k=2)

    assert [passage.chunk_id for passage in fused] == ["exact-hit", "dense-first"]
    assert fused[0].score == 0.7


class HybridCollection:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        if "where_document" in kwargs:
            return {
                "ids": [["exact-hit"]],
                "documents": [["section 1.17 exact wording"]],
                "metadatas": [[{
                    "source": "rules.pdf", "section": "1.17", "page": 2,
                    "doc_version": "2026", "superseded": False,
                }]],
                "distances": [[0.3]],
            }
        return {
            "ids": [["dense-first", "exact-hit"]],
            "documents": [["semantic match", "section 1.17 exact wording"]],
            "metadatas": [[
                {"source": "rules.pdf", "section": "5.1", "page": 1,
                 "doc_version": "2026", "superseded": False},
                {"source": "rules.pdf", "section": "1.17", "page": 2,
                 "doc_version": "2026", "superseded": False},
            ]],
            "distances": [[0.1, 0.3]],
        }


class HybridClient:
    def __init__(self) -> None:
        self.collection = HybridCollection()

    def get_collection(self, *, name, embedding_function):
        assert name == "rahbar-v1"
        assert embedding_function is None
        return self.collection


class HybridIndexState:
    def current(self):
        return IndexStatus(
            active="rahbar-v1",
            previous=None,
            metadata={"embed_model": "dummy-768"},
            checks={"collection": "ok"},
        )


def test_chroma_hybrid_uses_exact_term_filter_and_rrf() -> None:
    client = HybridClient()
    retriever = ChromaRetriever(
        Settings(embed_model="dummy-768", hybrid_retrieval=True),
        client,
        DummyEmbedder(),
        HybridIndexState(),
    )

    passages = retriever.retrieve(
        RetrievalQuery("clause 1.17", [0.0] * 768, 2, exact_terms=["1.17"])
    )

    assert len(client.collection.calls) == 2
    assert client.collection.calls[1]["where_document"] == {"$contains": "1.17"}
    assert passages[0].chunk_id == "exact-hit"
