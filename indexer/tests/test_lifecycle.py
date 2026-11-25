"""A1 + A2 end to end with a fake Chroma: verify, quarantine, lake, archive, incremental update,
deletion without orphans and version restore. Batch A = the CI fixtures, Batch B = the
committed planted batch."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import hashlib
import math
import re

import pytest

from pipeline import embed as embed_module
from pipeline import run, store
from pipeline.config import get_settings
from pipeline.lake import DataLake
from pipeline.tokens import WhitespaceTokenCounter
from test_starter_dummy import FakeClient

ROOT = Path(__file__).resolve().parents[2]
BATCH_B = ROOT / "eval" / "batches" / "batch-b"
EXPECTED = json.loads((ROOT / "eval" / "batches" / "expected-dispositions.json").read_text())


def bag_of_words(texts, _settings=None):
    """A tiny stand-in embedder: similar wording gives a similar vector."""
    vectors = []
    for text in texts:
        vector = [0.0] * 64
        for word in re.findall(r"\w+", text.casefold()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        vectors.append([v / norm for v in vector])
    return vectors


@pytest.fixture
def env(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    shutil.copytree(ROOT / "eval" / "fixtures", corpus,
                    ignore=shutil.ignore_patterns("*.json", "*.yaml", "README.md"))
    client = FakeClient()
    monkeypatch.setattr(store, "get_client", lambda _settings: client)
    monkeypatch.setattr(run, "get_tokenizer", lambda *_args: WhitespaceTokenCounter())
    monkeypatch.setattr(embed_module, "embed", bag_of_words)
    settings = replace(get_settings(), embed_model="dummy-768", corpus_dir=str(corpus),
                       pipeline_data_dir=str(tmp_path / "data"), chunk_size=120,
                       chunk_overlap=10)
    return settings, corpus, client


def active_rows(client):
    pointer = client.collections["rahbar-active"].metadata
    return client.collections[pointer["active"]].rows


def chunks_by_source(client):
    counts: dict[str, int] = {}
    for _text, _vector, meta in active_rows(client).values():
        counts[meta["source"]] = counts.get(meta["source"], 0) + 1
    return counts


def report(result):
    return json.loads(Path(result["verification_report"]).read_text())


def test_batch_a_then_unchanged_rerun_embeds_zero_chunks(env):
    settings, _corpus, client = env
    first = report(run.run_pipeline(settings))
    assert first["summary"]["verified"] == 3 and first["summary"]["quarantined"] == 0
    assert first["summary"]["embedded_chunks"] > 0
    superseded = {m["source"] for _t, _v, m in active_rows(client).values() if m["superseded"]}
    assert superseded == {"academic-rules-2023.md"}          # recency, detected automatically
    archived = Path(settings.pipeline_data_dir, "archive", "academic-rules", "2023",
                    "academic-rules-2023.md")
    assert archived.is_file()

    collection = client.collections["rahbar-active"].metadata["active"]
    second = report(run.run_pipeline(settings))
    assert second["summary"]["embedded_chunks"] == 0
    assert second["summary"]["unchanged"] == 3 and second["summary"]["verified"] == 0
    assert second["incremental"]["published"] is False
    assert client.collections["rahbar-active"].metadata["active"] == collection


def test_batch_b_quarantines_every_planted_fault_and_indexes_the_rest(env):
    settings, _corpus, client = env
    run.run_pipeline(settings)
    result = report(run.run_pipeline(settings, batch_dir=str(BATCH_B)))
    disposition = {d["source"]: d["disposition"] for d in result["documents"]}
    expected = EXPECTED["batch_b"]["expected"]
    assert {s for s, d in disposition.items() if d == "quarantine"} == set(expected["quarantine"])
    assert {s for s, d in disposition.items() if d == "accept"} == set(expected["accept"])
    for source in expected["quarantine"]:
        moved = Path(next(d["moved_to"] for d in result["documents"] if d["source"] == source))
        assert moved.is_file() and "quarantine" in moved.parts
        assert moved.with_name(moved.name + ".reason.json").is_file()
    indexed = chunks_by_source(client)
    assert not set(expected["quarantine"]) & set(indexed)
    assert set(expected["accept"]) <= set(indexed)
    assert result["summary"]["unchanged"] == 3            # Batch A reused, not re-embedded


def test_changed_document_replaces_only_its_own_chunks_and_archives_old_file(env):
    settings, corpus, client = env
    run.run_pipeline(settings)
    before = {i: m for i, (_t, _v, m) in active_rows(client).items()}
    fees = corpus / "fees-2026.md"
    fees.write_text(fees.read_text().replace("No refund is given", "No refund at all is given"))
    result = report(run.run_pipeline(settings))
    assert result["incremental"]["changed"] == ["fees-2026.md"]
    assert result["incremental"]["embedded_documents"] == ["fees-2026.md"]
    after = {i: m for i, (_t, _v, m) in active_rows(client).items()}
    untouched = [i for i, m in before.items() if m["source"] != "fees-2026.md"]
    assert all(i in after for i in untouched)
    assert any("archived replaced fees-2026.md" in a for a in result["lake_actions"])


def test_deleted_document_leaves_no_orphans_and_can_be_restored(env):
    settings, corpus, client = env
    run.run_pipeline(settings)
    (corpus / "fees-2026.md").unlink()
    result = report(run.run_pipeline(settings))
    assert result["incremental"]["deleted"] == ["fees-2026.md"]
    assert "fees-2026.md" not in chunks_by_source(client)       # count by document id = 0
    lake = DataLake(settings.pipeline_data_dir)
    assert lake.entries["fees-2026.md"].status == "deleted"
    assert Path(lake.entries["fees-2026.md"].path).is_file()     # archived, not destroyed

    lake.restore("fees-2026.md")
    lake.save()
    run.run_pipeline(settings)
    assert chunks_by_source(client)["fees-2026.md"] > 0


def test_superseded_version_restore_flips_metadata_without_re_embedding(env):
    settings, _corpus, client = env
    run.run_pipeline(settings)
    lake = DataLake(settings.pipeline_data_dir)
    action = lake.restore("academic-rules-2023.md", "2023")
    lake.save()
    assert "restored academic-rules-2023.md 2023" in action
    result = report(run.run_pipeline(settings))
    flags = {m["source"]: m["superseded"] for _t, _v, m in active_rows(client).values()}
    assert flags["academic-rules-2023.md"] is False and flags["academic-rules-2026.md"] is True
    assert result["summary"]["embedded_chunks"] == 0
    assert sorted(result["incremental"]["superseded_flag_changes"]) == [
        "academic-rules-2023.md", "academic-rules-2026.md"]
