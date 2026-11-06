"""Deterministic dummy query vectors for local and failure-stage checks."""

from __future__ import annotations

import hashlib
import math


class DummyEmbedder:
    model_name = "dummy-768"
    dimension = 768

    def embed_query(self, text: str) -> list[float]:
        values: list[float] = []
        counter = 0
        while len(values) < self.dimension:
            digest = hashlib.sha256(f"{text}\0{counter}".encode()).digest()
            for offset in range(0, len(digest), 4):
                integer = int.from_bytes(digest[offset : offset + 4], "big")
                values.append((integer / 2**31) - 1)
            counter += 1
        values = values[: self.dimension]
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]
