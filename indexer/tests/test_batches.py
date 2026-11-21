import json
from pathlib import Path

from pipeline.extract import extract
from pipeline.run import discover
from pipeline.verify import verify_documents


def test_batch_b_matches_planted_document_dispositions():
    root = Path(__file__).resolve().parents[2]
    batches = root / "eval" / "batches"
    expected = json.loads((batches / "expected-dispositions.json").read_text(encoding="utf-8"))
    documents = [extract(str(path), version, superseded)
                 for path, version, superseded in discover(str(batches / "batch-b"))]
    results = {item.source: item for item in verify_documents(documents)}

    assert len(documents) == expected["batch_b"]["documents"]
    assert sorted(name for name, result in results.items() if result.passed) == sorted(
        expected["batch_b"]["expected"]["pass"]
    )
    assert sorted(name for name, result in results.items() if not result.passed) == sorted(
        expected["batch_b"]["expected"]["quarantine"]
    )
    assert results["academic-rules-2023.md"].passed
    assert results["academic-rules-2026.md"].passed
    assert results["academic-rules-2027.md"].passed
    superseded = {path.name for path, _version, old in discover(str(batches / "batch-b")) if old}
    assert superseded == set(expected["batch_b"]["expected"]["superseded"])
    assert results["injected-instruction.md"].passed


def test_clean_batch_b_is_ingestable_and_marks_superseded_versions():
    root = Path(__file__).resolve().parents[2]
    batches = root / "eval" / "batches"
    expected = json.loads((batches / "expected-dispositions.json").read_text(encoding="utf-8"))
    found = discover(str(batches / "batch-b-clean"))
    documents = [extract(str(path), version, superseded) for path, version, superseded in found]
    results = verify_documents(documents)

    assert len(documents) == expected["batch_b_clean"]["documents"]
    assert all(result.passed for result in results)
    assert {path.name for path, _version, old in found if old} == set(
        expected["batch_b_clean"]["superseded"]
    )

