import sys
from types import ModuleType

from pipeline.config import get_settings
from pipeline.embed import EMBED_BATCH_SIZE, embed


def test_dummy_embedding_is_deterministic_and_unit_length() -> None:
    settings = get_settings()
    from dataclasses import replace

    settings = replace(settings, embed_model="dummy-768")
    first = embed(["same", "different"], settings)
    assert first == embed(["same", "different"], settings)
    assert len(first) == 2 and len(first[0]) == 768
    assert abs(sum(value * value for value in first[0]) - 1) < 1e-9


def test_fastembed_batches_32_and_uses_baked_cache(monkeypatch) -> None:
    instances = []

    class Vector(list):
        def astype(self, _dtype):
            return self

        def tolist(self):
            return list(self)

    class FakeTextEmbedding:
        def __init__(self, model_name, cache_dir):
            instances.append((model_name, cache_dir, []))

        def embed(self, texts, batch_size):
            instances[-1][2].append((len(texts), batch_size))
            return [Vector([float(len(texts)), 1.0]) for _ in texts]

    fake_module = ModuleType("fastembed")
    fake_module.TextEmbedding = FakeTextEmbedding
    monkeypatch.setitem(sys.modules, "fastembed", fake_module)
    from dataclasses import replace

    settings = replace(get_settings(), embed_model="BAAI/bge-small-en-v1.5", embed_cache_dir="/models")
    vectors = embed([str(i) for i in range(65)], settings)
    assert len(vectors) == 65 and all(len(vector) == 2 for vector in vectors)
    assert instances == [("BAAI/bge-small-en-v1.5", "/models", [(32, EMBED_BATCH_SIZE), (32, EMBED_BATCH_SIZE), (1, EMBED_BATCH_SIZE)])]


def test_empty_embedding_does_not_load_model(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    assert embed([], settings) == []
