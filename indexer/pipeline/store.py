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
    source_digests: dict[str, str] | None = None,
    incremental: dict[str, Any] | None = None,
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
        "source_digests": json.dumps(source_digests or {}, sort_keys=True),
        "document_chunk_counts": json.dumps(_chunk_counts(chunks), sort_keys=True),
        "incremental_summary": json.dumps(incremental or {}, sort_keys=True),
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

    # modify() replaces the whole metadata dictionary, so send every key again, but never the
    # hnsw:* keys: the distance function is fixed at creation and chromadb-client refuses a
    # modify() that carries hnsw:space. The collection stays cosine.
    complete_metadata = {k: v for k, v in metadata.items() if not k.startswith("hnsw:")}
    collection.modify(metadata={**complete_metadata, "status": "complete"})

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


def _chunk_counts(chunks: list[Chunk]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk.source] = counts.get(chunk.source, 0) + 1
    return counts


def active_snapshot(settings: IndexerSettings, client: Any | None = None) -> dict[str, Any]:
    """Read the active index's per-document digests, records and vectors."""
    client = client or get_client(settings)
    pointer_name = f"{settings.collection}-active"
    names = {_collection_name(item) for item in client.list_collections()}
    if pointer_name not in names:
        return {"metadata": {}, "records": {}, "source_digests": {}, "chunk_counts": {}}
    pointer = client.get_collection(name=pointer_name, embedding_function=None)
    active = str((pointer.metadata or {}).get("active", ""))
    if not active or active not in names:
        return {"metadata": {}, "records": {}, "source_digests": {}, "chunk_counts": {}}
    collection = client.get_collection(name=active, embedding_function=None)
    metadata = dict(collection.metadata or {})
    rows = collection.get(include=["documents", "metadatas", "embeddings"])
    records: dict[str, dict[str, Any]] = {}
    for identifier, document, row_metadata, embedding in zip(
        rows.get("ids", []), rows.get("documents", []), rows.get("metadatas", []),
        rows.get("embeddings", []),
    ):
        vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        records[str(identifier)] = {
            "document": document, "metadata": row_metadata or {}, "embedding": vector,
        }
    try:
        digests = json.loads(str(metadata.get("source_digests", "{}")))
        counts = json.loads(str(metadata.get("document_chunk_counts", "{}")))
    except (TypeError, json.JSONDecodeError):
        digests, counts = {}, {}
    if not counts:
        for row in records.values():
            source = str(row["metadata"].get("source", ""))
            if source:
                counts[source] = counts.get(source, 0) + 1
    return {"metadata": metadata, "records": records,
            "source_digests": digests, "chunk_counts": counts}


def plan_incremental(
    chunks: list[Chunk], source_digests: dict[str, str], settings: IndexerSettings,
    snapshot: dict[str, Any],
) -> tuple[dict[str, list[float]], dict[str, Any]]:
    """Return reusable chunk vectors and a document-level before/after summary."""
    old_digests: dict[str, str] = snapshot.get("source_digests", {})
    old_sources, current_sources = set(old_digests), set(source_digests)
    added = sorted(current_sources - old_sources)
    deleted = sorted(old_sources - current_sources)
    changed = sorted(source for source in current_sources & old_sources
                     if source_digests[source] != old_digests[source])
    unchanged = sorted((current_sources & old_sources) - set(changed))
    previous_meta = snapshot.get("metadata", {})
    compatible = (
        previous_meta.get("embed_model") == settings.embed_model
        and previous_meta.get("chunk_size") == settings.chunk_size
        and previous_meta.get("chunk_overlap") == settings.chunk_overlap
        and previous_meta.get("chunk_strategy") == settings.chunk_strategy
    )
    old_records: dict[str, dict[str, Any]] = snapshot.get("records", {})
    current_by_source: dict[str, list[Chunk]] = {}
    old_by_source: dict[str, dict[str, dict[str, Any]]] = {}
    for chunk in chunks:
        current_by_source.setdefault(chunk.source, []).append(chunk)
    for identifier, record in old_records.items():
        source = str(record["metadata"].get("source", ""))
        old_by_source.setdefault(source, {})[identifier] = record

    reusable: dict[str, list[float]] = {}
    reused_documents: list[str] = []
    for source in unchanged if compatible else []:
        current_rows = current_by_source.get(source, [])
        old_rows = old_by_source.get(source, {})
        if (len(current_rows) != len(old_rows)
                or any(chunk.id not in old_rows
                       or old_rows[chunk.id]["document"] != chunk.text
                       or not old_rows[chunk.id]["embedding"]
                       for chunk in current_rows)):
            continue
        for chunk in current_rows:
            reusable[chunk.id] = old_rows[chunk.id]["embedding"]
        reused_documents.append(source)

    new_counts = _chunk_counts(chunks)
    old_counts: dict[str, int] = snapshot.get("chunk_counts", {})
    summary = {
        "added": added,
        "changed": changed,
        "unchanged": unchanged,
        "deleted": deleted,
        "reused_documents": sorted(reused_documents),
        "embedded_documents": sorted(set(current_by_source) - set(reused_documents)),
        "reused_chunks": len(reusable),
        "embedded_chunks": len(chunks) - len(reusable),
        "document_chunk_counts_before": old_counts,
        "document_chunk_counts_after": new_counts,
        "model_or_chunk_config_changed": not compatible and bool(previous_meta),
    }
    return reusable, summary


def restore_previous(settings: IndexerSettings, client: Any | None = None) -> str:
    """Swap the active pointer to its previous complete collection."""
    client = client or get_client(settings)
    pointer_name = f"{settings.collection}-active"
    names = {_collection_name(item) for item in client.list_collections()}
    if pointer_name not in names:
        raise ValueError(f"active index pointer {pointer_name} does not exist")
    pointer = client.get_collection(name=pointer_name, embedding_function=None)
    metadata = dict(pointer.metadata or {})
    current, previous = str(metadata.get("active", "")), str(metadata.get("previous", ""))
    if not previous or previous not in names:
        raise ValueError("no previous index collection is available to restore")
    restored = client.get_collection(name=previous, embedding_function=None)
    if (restored.metadata or {}).get("status") != "complete":
        raise ValueError(f"previous index {previous} is not complete")
    pointer.modify(metadata={
        **metadata, "active": previous, "previous": current,
        "activated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    })
    return previous


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
