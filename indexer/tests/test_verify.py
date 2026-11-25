"""A1: the four verification checks, each with a pass/fail and a reason."""

from pipeline.models import Document, Page
from pipeline.verify import Candidate, KnownDocument, text_digest, verify_documents

BODY = ("1.1 A student must attend at least 80 percent of lectures to sit the final "
        "examination. 1.2 A student below the minimum attendance receives the grade FA. "
        "2.1 A CGPA below 2.00 at the end of a regular semester places the student on "
        "academic warning, and three warnings close the admission.")


def candidate(source="rules-2026.md", text=BODY, version="2026", doc_id="rules",
              title="Academic Rules", pages=None, file_type="md", raw_tail=b"",
              extracted=True) -> Candidate:
    document = None
    if extracted:
        document = Document(source, version, False,
                            [Page(source, i + 1, part) for i, part in enumerate(pages or [text])])
    return Candidate(document, source, doc_id, version, title, file_type,
                     raw_tail=raw_tail, extraction_error="" if extracted else "Unexpected EOF")


def checks(result):
    return {name: check.passed for name, check in result.checks.items()}


def test_complete_unique_current_document_passes_every_check():
    (result,) = verify_documents([candidate()])
    assert checks(result) == {"quality": True, "completeness": True, "recency": True,
                              "uniqueness": True}
    assert result.disposition == "accept"
    assert all(check.reason for check in result.checks.values())


def test_quality_fails_failed_empty_garbled_and_too_short_extractions():
    failed, empty, garbled, short = verify_documents([
        candidate("a.pdf", extracted=False, file_type="pdf"),
        candidate("b.md", text=" "), candidate("c.md", text="@@ ## %% $$ " * 40 + "."),
        candidate("d.md", text="Too short."),
    ])
    assert "extraction failed: Unexpected EOF" in failed.checks["quality"].reason
    assert empty.checks["quality"].reason == "extracted text is empty"
    assert "garbled" in garbled.checks["quality"].reason
    assert "too short" in short.checks["quality"].reason
    assert {r.disposition for r in (failed, empty, garbled, short)} == {"quarantine"}


def test_completeness_fails_missing_metadata_and_truncation():
    no_meta, cut_text, cut_pdf = verify_documents([
        candidate("clubs.md", title="", version="unknown", doc_id="clubs"),
        candidate("notice.md", text=BODY + " Route 3 now serves G-9, G-10 and", doc_id="n"),
        candidate("t.pdf", file_type="pdf", raw_tail=b"endobj\nxref", doc_id="t"),
    ])
    assert no_meta.checks["completeness"].reason == "missing title; missing date/version"
    assert "ends mid-sentence" in cut_text.checks["completeness"].reason
    assert "no %%EOF" in cut_pdf.checks["completeness"].reason
    assert cut_text.disposition == "quarantine"


def test_recency_fails_the_older_version_in_a_batch_and_archives_it():
    old, new = verify_documents([candidate("rules-2026.md", version="2026"),
                                 candidate("rules-2027.md", version="2027",
                                           text=BODY.replace("80", "75"))])
    assert not old.checks["recency"].passed
    assert "newer version 2027 detected (rules-2027.md)" in old.checks["recency"].reason
    assert old.disposition == "archive-superseded"
    assert new.checks["recency"].passed and "supersedes rules-2026.md" in \
        new.checks["recency"].reason


def test_recency_compares_with_versions_already_in_the_lake():
    known = [KnownDocument("rules-2027.md", "rules", "2027", "current", "x", [])]
    (result,) = verify_documents([candidate("rules-2023.md", version="2023")], known=known)
    assert result.disposition == "archive-superseded"


def test_uniqueness_detects_exact_duplicates_in_batch_and_lake():
    known = [KnownDocument("handbook.md", "handbook", "2026", "current",
                           text_digest(" ".join(BODY.split())), [])]
    in_lake, original, copy = verify_documents([
        candidate("copy-of-handbook.md", doc_id="other"),
        candidate("library.md", text=BODY.replace("80", "90"), doc_id="library"),
        candidate("library_copy.md", text=BODY.replace("80", "90"), doc_id="library-copy"),
    ], known=known)
    assert "exact duplicate of handbook.md" in in_lake.checks["uniqueness"].reason
    assert original.disposition == "accept"
    assert "exact duplicate of library.md" in copy.checks["uniqueness"].reason


def test_uniqueness_detects_near_duplicates_with_embeddings():
    def embed(texts):   # two near-identical texts map to near-identical vectors
        return [[1.0, 0.02 * ("Students" in text), 0.0] for text in texts]

    original, draft, other = verify_documents([
        candidate("exam.md", doc_id="exam"),
        candidate("exam_draft.md", text=BODY.replace("A student", "Students", 1), doc_id="d"),
        candidate("fees.md", text=BODY, doc_id="fees", version="2026"),
    ], embed=lambda texts: [[0.0, 0.0, 1.0] if "fees" in t else v
                            for t, v in zip(texts, embed(texts))])
    assert original.disposition == "accept"
    assert "near-duplicate of exam.md" in draft.checks["uniqueness"].reason


def test_versions_of_one_document_are_a_recency_question_not_a_duplicate():
    old, new = verify_documents([candidate("rules-2023.md", version="2023"),
                                 candidate("rules-2026.md", version="2026")])
    assert old.checks["uniqueness"].passed and new.checks["uniqueness"].passed
