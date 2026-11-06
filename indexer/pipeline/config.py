"""Indexer configuration, from the same ConfigMap the API reads (section 4.1)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IndexerSettings:
    embed_model: str        # EMBED_MODEL: must equal the API's value (section 4.4)
    embed_cache_dir: str
    chroma_host: str
    chroma_port: int
    collection: str
    corpus_dir: str         # where the documents and _index.json sit inside the Job's pod
    chunk_size: int
    chunk_overlap: int
    chunk_strategy: str
    keep_collections: int
    index_refresh_seconds: int
    ollama_url: str


def get_settings() -> IndexerSettings:
    return IndexerSettings(
        embed_model=os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5"),
        embed_cache_dir=os.environ.get("EMBED_CACHE_DIR", "/models"),
        chroma_host=os.environ.get("CHROMA_HOST", "chroma"),
        chroma_port=int(os.environ.get("CHROMA_PORT", 8000)),
        collection=os.environ.get("CHROMA_COLLECTION", "rahbar"),
        corpus_dir=os.environ.get("CORPUS_DIR", "/corpus"),
        chunk_size=int(os.environ.get("CHUNK_SIZE", 400)),
        chunk_overlap=int(os.environ.get("CHUNK_OVERLAP", 50)),
        chunk_strategy=os.environ.get("CHUNK_STRATEGY", "structure"),
        keep_collections=int(os.environ.get("KEEP_COLLECTIONS", 2)),
        index_refresh_seconds=int(os.environ.get("INDEX_REFRESH_SECONDS", 10)),
        ollama_url=os.environ.get("OLLAMA_URL", "http://host.minikube.internal:11434"),
    )
