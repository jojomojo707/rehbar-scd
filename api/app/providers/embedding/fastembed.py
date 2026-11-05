"""FastEmbed query vectors matching the indexer's model pin."""

from __future__ import annotations

class FastEmbedder:
    def __init__(self, model_name: str, cache_dir: str = "/models") -> None:
        from fastembed import TextEmbedding

        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
        self.dimension = 384 if "bge-small-en-v1.5" in model_name else 0

    def embed_query(self, text: str) -> list[float]:
        vector = next(iter(self._model.query_embed(text)))
        values = [float(value) for value in vector.tolist()]
        if self.dimension == 0:
            self.dimension = len(values)
        return values
