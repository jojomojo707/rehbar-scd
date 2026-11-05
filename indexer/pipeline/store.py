"""Stage 5: Store. The only code in the whole system that writes to Chroma."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import IndexerSettings
from .models import Chunk


def get_client(settings: IndexerSettings) -> Any:
    import chromadb  # the thin client, from chromadb-client in requirements.txt
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                               settings=ChromaSettings(anonymized_telemetry=False))


def store(
    chunks: list[Chunk], vectors: list[list[float]], settings: IndexerSettings,
    client: Any | None = None,
    original_tokens: int | None = None,
) -> int:
    """Write every chunk with its vector and metadata, and record the embedding model
    and vector dimension in the collection metadata (section 4.4). Return the count."""
    if not chunks:
        raise ValueError("refusing to activate an empty index")
    if len(chunks) != len(vectors):
        raise ValueError(f"received {len(chunks)} chunks but {len(vectors)} vectors")
    dimension = len(vectors[0])
    if dimension == 0 or any(len(vector) != dimension for vector in vectors):
        raise ValueError("all embeddings must have the same non-zero dimension")

    client = client or get_client(settings)
    prefix = settings.collection
    pointer_name = f"{prefix}-active"
    existing = {_collection_name(item) for item in client.list_collections()}
    stamp = datetime.now(UTC).strftime(f"{prefix}-v%Y%m%d-%H%M%S")
    version = stamp
    suffix = 1
    while version in existing:
        version = f"{stamp}-{suffix:02d}"
        suffix += 1

    created_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    tokens = [int(getattr(chunk, "tokens", 0) or len(chunk.text.split())) for chunk in chunks]
    superseded_versions = sorted({c.doc_version for c in chunks if c.superseded})
    metadata: dict[str, str | int | float | bool] = {
        "hnsw:space": "cosine",
        "embed_model": settings.embed_model,
        "dimension": dimension,
        "index_version": version,
        "status": "building",
        "created_at": created_at,
        "chunk_count": len(chunks),
        "document_count": len({c.source for c in chunks}),
        "skipped_documents": 0,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "chunk_strategy": settings.chunk_strategy,
        "original_tokens": original_tokens if original_tokens is not None else sum(tokens),
        "stored_tokens": sum(tokens),
        "superseded_versions": ",".join(superseded_versions),
        "corpus_digest": _corpus_digest(settings.corpus_dir, chunks),
        "indexer_image": os.environ.get("IMAGE_TAG", ""),
    }
    collection = client.create_collection(
        name=version, metadata=metadata, embedding_function=None
    )
    for start in range(0, len(chunks), 256):
        batch_chunks = chunks[start:start + 256]
        batch_vectors = vectors[start:start + 256]
        collection.add(
            ids=[chunk.id for chunk in batch_chunks],
            documents=[chunk.text for chunk in batch_chunks],
            embeddings=batch_vectors,
            metadatas=[chunk.metadata() for chunk in batch_chunks],
        )
    written = int(collection.count())
    if written != len(chunks):
        raise RuntimeError(f"new index has {written} chunks; expected {len(chunks)}")

    complete_metadata = {**metadata, "status": "complete"}
    collection.modify(metadata=complete_metadata)

    previous = ""
    if pointer_name in existing:
        pointer = client.get_collection(name=pointer_name, embedding_function=None)
        previous = str((pointer.metadata or {}).get("active", ""))
        pointer_metadata = {
            **dict(pointer.metadata or {}),
            "active": version,
            "previous": previous,
            "activated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        pointer.modify(metadata=pointer_metadata)
    else:
        client.create_collection(
            name=pointer_name,
            metadata={
                "active": version,
                "previous": "",
                "activated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            },
            embedding_function=None,
        )

    _prune(client, prefix, version, previous, max(2, settings.keep_collections))
    return written


def _collection_name(item: Any) -> str:
    return item if isinstance(item, str) else str(item.name)


def _corpus_digest(corpus_dir: str, chunks: list[Chunk]) -> str:
    root = Path(corpus_dir)
    index_path = root / "_index.json"
    if index_path.exists():
        entries = json.loads(index_path.read_text(encoding="utf-8"))
        checksums = sorted(f"{entry['file']}:{entry['sha256']}" for entry in entries)
    else:
        checksums = []
        for source in sorted({chunk.source for chunk in chunks}):
            file_path = root / source
            if file_path.is_file():
                checksums.append(f"{source}:{hashlib.sha256(file_path.read_bytes()).hexdigest()}")
            else:
                checksums.append(source)
    return hashlib.sha256("\n".join(checksums).encode("utf-8")).hexdigest()


def _prune(client: Any, prefix: str, active: str, previous: str, keep: int) -> None:
    names = [_collection_name(item) for item in client.list_collections()]
    versions = [name for name in names if name.startswith(f"{prefix}-v")]
    protected = {active, previous}
    complete = []
    old_building = []
    now = datetime.now(UTC)
    for name in versions:
        if name in protected:
            continue
        collection = client.get_collection(name=name, embedding_function=None)
        metadata = dict(collection.metadata or {})
        if metadata.get("status") == "complete":
            complete.append((str(metadata.get("created_at", "")), name))
        elif metadata.get("status") == "building":
            try:
                created = datetime.fromisoformat(str(metadata["created_at"]).replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            if now - created > timedelta(hours=6):
                old_building.append(name)
    keep_count = max(0, keep - len(protected - {""}))
    keep_extra = {name for _created, name in sorted(complete, reverse=True)[:keep_count]}
    for name in versions:
        if name not in protected and name not in keep_extra and name not in old_building:
            metadata = client.get_collection(name=name, embedding_function=None).metadata or {}
            if metadata.get("status") == "complete":
                client.delete_collection(name=name)
    for name in old_building:
        client.delete_collection(name=name)
