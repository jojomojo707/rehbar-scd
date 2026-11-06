"""Read the active blue/green Chroma collection and map hits to passages."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, cast

from ..config import Settings
from ..providers.embedding.base import Embedder
from ..schemas import Passage
from ..services.index_state import IndexState
from .base import RetrievalQuery


class ChromaRetriever:
    name = "chroma"

    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
        embedder: Embedder | None = None,
        index_state: IndexState | None = None,
    ) -> None:
        if client is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            client = chromadb.HttpClient(
                host=settings.chroma_host,
                port=settings.chroma_port,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        self.settings = settings
        self.client = client
        self.index_state = index_state or IndexState(settings, client=client)
        if embedder is None:
            if settings.embed_model == "dummy-768":
                from ..providers.embedding.dummy import DummyEmbedder

                embedder = DummyEmbedder()
            else:
                from ..providers.embedding.fastembed import FastEmbedder

                embedder = FastEmbedder(settings.embed_model, settings.embed_cache_dir)
        self.embedder = embedder

    def retrieve(self, query: RetrievalQuery | str, k: int | None = None) -> list[Passage]:
        if isinstance(query, str):
            from ..services.query_intent import make_retrieval_query
            from ..routes.metrics import EMBEDDING

            state = self.index_state.current()
            versions = str(state.metadata.get("superseded_versions", "")).split(",")
            versions = [version.strip() for version in versions if version.strip()]
            started = time.perf_counter()
            query = make_retrieval_query(
                query, k or self.settings.top_k, state.active or "", self.embedder, versions
            )
            EMBEDDING.observe(time.perf_counter() - started)
        status = self.index_state.current()
        if not status.ready or not status.active:
            raise RuntimeError(f"active index is not ready: {status.failed or status.checks}")
        metadata = status.metadata
        if metadata.get("embed_model") != self.settings.embed_model:
            raise RuntimeError(
                f"active index uses {metadata.get('embed_model')!r}, "
                f"API is configured for {self.settings.embed_model!r}"
            )
        vector = query.vector or self.embedder.embed_query(query.text)
        collection = self.client.get_collection(name=status.active, embedding_function=None)
        where = (
            None
            if query.include_superseded or not self.settings.superseded_filter
            else {"superseded": False}
        )
        hybrid = self.settings.hybrid_retrieval and bool(query.exact_terms)
        dense_limit = max(query.k, query.k * 5) if hybrid else max(
            query.k, query.k * 5 if query.requested_year else query.k
        )
        dense_result = collection.query(
            query_embeddings=cast(Any, [vector]),
            n_results=dense_limit,
            where=cast(Any, where),
            include=["documents", "metadatas", "distances"],
        )
        dense_passages = _passages_from_result(
            dense_result, query, dense_limit, self.settings.superseded_filter
        )
        if not hybrid:
            return dense_passages[:query.k]

        from .fusion import reciprocal_rank_fusion

        rankings = [dense_passages]
        for term in query.exact_terms:
            exact_result = collection.query(
                query_embeddings=cast(Any, [vector]),
                n_results=max(query.k * 5, query.k),
                where=cast(Any, where),
                where_document=cast(Any, {"$contains": term}),
                include=["documents", "metadatas", "distances"],
            )
            rankings.append(
                _passages_from_result(
                    exact_result,
                    query,
                    max(query.k * 5, query.k),
                    self.settings.superseded_filter,
                )
            )
        return reciprocal_rank_fusion(rankings, query.k)


def _passages_from_result(
    result: Mapping[str, object],
    query: RetrievalQuery,
    limit: int,
    superseded_filter: bool,
) -> list[Passage]:
    ids = _first(result.get("ids"))
    texts = _first(result.get("documents"))
    metadatas = _first(result.get("metadatas"))
    distances = _first(result.get("distances"))
    passages: list[Passage] = []
    for chunk_id, text, raw_meta, distance in zip(ids, texts, metadatas, distances):
        meta = raw_meta or {}
        version = str(meta.get("doc_version", ""))
        if query.requested_year and query.requested_year not in version:
            continue
        if (
            superseded_filter
            and not query.include_superseded
            and bool(meta.get("superseded", False))
        ):
            continue
        passages.append(Passage(
            chunk_id=str(chunk_id),
            text=str(text),
            source=str(meta.get("source", "unknown")),
            section=str(meta.get("section", "")),
            page=_optional_int(meta.get("page")),
            score=1.0 - float(distance),
            doc_version=str(meta.get("doc_version", "unknown")),
            superseded=bool(meta.get("superseded", False)),
        ))
        if len(passages) >= limit:
            break
    return passages


def _first(value: Any) -> list[Any]:
    if not value:
        return []
    return list(value[0] or [])


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
