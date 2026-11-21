import json

import pytest

from pipeline import run
from pipeline.config import IndexerSettings
from pipeline.models import Document, Page
from pipeline.verify import CheckResult, DocumentVerification


def settings(corpus_dir):
    return IndexerSettings(
        embed_model="pinned", embed_cache_dir="/models", chroma_host="chroma",
        chroma_port=8000, collection="rahbar", corpus_dir=str(corpus_dir),
        chunk_size=400, chunk_overlap=50, chunk_strategy="structure",
        keep_collections=2, index_refresh_seconds=10, ollama_url="http://ollama",
    )


def test_failed_document_is_copied_and_reported_per_run(tmp_path):
    source = tmp_path / "bad.pdf"
    source.write_bytes(b"preserve this rejected input")
    report_path = run._persist_verification_artifacts(
        [{"source": "bad.pdf", "path": str(source), "passed": False,
          "checks": {"quality": {"passed": False, "reason": "truncated"}}}],
        run_id="run-one", quarantine_dir=str(tmp_path / "quarantine"),
        report_dir=str(tmp_path / "reports"),
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    quarantined = tmp_path / "quarantine" / "run-one" / "0001-bad.pdf"
    assert quarantined.read_bytes() == source.read_bytes()
    assert report["run_id"] == "run-one"
    assert report["summary"] == {"documents": 1, "failed": 1, "passed": 0}
    assert report["documents"][0]["quarantined_to"] == str(quarantined)


def test_verification_failure_stops_before_chunk_embed_or_store(tmp_path, monkeypatch):
    source = tmp_path / "bad.md"
    source.write_text("bad content", encoding="utf-8")
    monkeypatch.setenv("QUARANTINE_DIR", str(tmp_path / "quarantine"))
    monkeypatch.setenv("VERIFICATION_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(run, "discover", lambda _: [(source, "2026", False)])

    import pipeline.chunk
    import pipeline.clean
    import pipeline.embed
    import pipeline.extract
    import pipeline.store
    import pipeline.verify

    document = Document("bad.md", "2026", False,
                        [Page("bad.md", 1, "A document that failed verification.")])
    monkeypatch.setattr(pipeline.extract, "extract", lambda *_: document)
    monkeypatch.setattr(pipeline.verify, "verify_documents", lambda *_args, **_kwargs: [
        DocumentVerification("bad.md", {"quality": CheckResult(False, "rejected")})
    ])
    for module, name in ((pipeline.chunk, "chunk"), (pipeline.clean, "clean"),
                         (pipeline.embed, "embed"), (pipeline.store, "store")):
        monkeypatch.setattr(module, name, lambda *_args, **_kwargs: pytest.fail(
            f"{name} must not run for a failed verification batch"))

    with pytest.raises(ValueError, match="report="):
        run.run_pipeline(settings(tmp_path))

    reports = list((tmp_path / "reports").glob("*.json"))
    quarantined = list((tmp_path / "quarantine").glob("*/*"))
    assert len(reports) == 1
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "bad content"
