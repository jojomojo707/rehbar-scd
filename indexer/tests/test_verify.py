from pipeline.models import Document, Page
from pipeline.verify import verify_documents


def doc(source="rules.pdf", version="2026", text=None, pages=None):
    text = text if text is not None else "Academic policy states a meaningful rule for students."
    pages = pages if pages is not None else [Page(source, 1, text)]
    return Document(source, version, False, pages)


def test_verification_passes_complete_document():
    result = verify_documents([doc()])[0]
    assert result.passed
    assert set(result.checks) == {"quality", "completeness", "recency", "uniqueness"}


def test_quality_fails_empty_and_garbled_extractions():
    empty = verify_documents([doc(text="")])[0]
    garbled = verify_documents([doc(text="@@@###!!!%%%^^^&&&***(((())))")])[0]
    assert not empty.checks["quality"].passed
    assert "empty" in empty.checks["quality"].reason
    assert not garbled.checks["quality"].passed
    assert "garbled" in garbled.checks["quality"].reason


def test_completeness_fails_missing_version_and_invalid_page_sequence():
    item = doc(version="unknown", pages=[Page("rules.pdf", 2, "A sufficiently long policy passage with useful content.")])
    result = verify_documents([item])[0]
    assert not result.checks["completeness"].passed
    assert "date/version" in result.checks["completeness"].reason
    assert "complete page sequence" in result.checks["completeness"].reason


def test_recency_detects_newer_stored_version():
    result = verify_documents([doc(version="2023")], existing=[doc(version="2026")])[0]
    assert not result.checks["recency"].passed
    assert "2026" in result.checks["recency"].reason


def test_uniqueness_detects_exact_duplicate_and_embedding_near_duplicate():
    first = doc("one.pdf")
    duplicate = doc("copy.pdf")
    result = verify_documents([first, duplicate])[1]
    assert not result.checks["uniqueness"].passed
    assert "exact duplicate" in result.checks["uniqueness"].reason

    texts = []
    def fake_embed(values):
        texts.extend(values)
        return [[1.0, 0.0] if i == 0 else [0.99, 0.01] for i, _ in enumerate(values)]
    first, second = doc("a.pdf"), doc("b.pdf", text="A different policy passage with changed wording.")
    result = verify_documents([first, second], embed=fake_embed)[1]
    assert not result.checks["uniqueness"].passed
    assert "near-duplicate" in result.checks["uniqueness"].reason
