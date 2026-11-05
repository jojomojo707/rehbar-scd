"""Stage 4: Embed. One vector per chunk, from the pinned model only."""

from __future__ import annotations

from collections.abc import Iterator

from .config import IndexerSettings

EMBED_BATCH_SIZE = 32


def _batches(values: list[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def embed(texts: list[str], settings: IndexerSettings) -> list[list[float]]:
    """Embed with settings.embed_model and nothing else.

    The model directory is baked into the image at build time. Empty input avoids
    loading the model, and dummy-768 stays deterministic for cluster smoke tests.
    """
    if not texts:
        return []
    if settings.embed_model == "dummy-768":
        from .dummy import DUMMY_DIM, fake_vector

        return [fake_vector(text, DUMMY_DIM) for text in texts]

    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=settings.embed_model, cache_dir=settings.embed_cache_dir)
    vectors: list[list[float]] = []
    for batch in _batches(texts, EMBED_BATCH_SIZE):
        vectors.extend(vector.astype(float).tolist() for vector in model.embed(batch, batch_size=EMBED_BATCH_SIZE))
    if len(vectors) != len(texts):
        raise RuntimeError(f"embedding returned {len(vectors)} vectors for {len(texts)} texts")
    dimension = len(vectors[0])
    if dimension == 0 or any(len(vector) != dimension for vector in vectors):
        raise RuntimeError("embedding returned inconsistent or empty vector dimensions")
    return vectors
