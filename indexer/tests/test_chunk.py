from pipeline.chunk import chunk
from pipeline.models import Document, Page
from pipeline.tokens import WhitespaceTokenCounter


TOKENS = WhitespaceTokenCounter()


def document(text: str, *, ocr: bool = False) -> Document:
    return Document("rules.pdf", "2026", False, [Page("rules.pdf", 1, text, ocr)])


def test_chunk_respects_sections() -> None:
    doc = document("1 Attendance\nAttendance rule applies today. More attendance details follow.\n\n2 Grading\nGrades are calculated each semester.")
    chunks = chunk(doc, 9, 2, TOKENS)
    attendance = [c for c in chunks if c.section == "1 Attendance"]
    grading = [c for c in chunks if c.section == "2 Grading"]
    assert attendance and grading
    assert all(c.text.startswith("1 Attendance\n") for c in attendance)
    assert all(c.text.startswith("2 Grading\n") for c in grading)
    assert all("Grades are" not in c.text for c in attendance)


def test_chunk_overlap_within_section() -> None:
    doc = document("1 Rule\nalpha beta gamma delta epsilon zeta eta theta iota kappa.")
    chunks = chunk(doc, 7, 2, TOKENS)
    assert len(chunks) > 1
    for before, after in zip(chunks, chunks[1:]):
        assert before.section == after.section
        previous_words = before.text.split("\n", 1)[1].split()
        next_words = after.text.split("\n", 1)[1].split()
        overlap_size = 0
        for count in (2, 1):
            if previous_words[-count:] == next_words[:count]:
                overlap_size = count
                break
        assert overlap_size >= 1


def test_chunk_max_tokens_and_hard_limit_512() -> None:
    doc = document("1 Long Section\n" + " ".join(f"word{i}" for i in range(1100)))
    chunks = chunk(doc, 900, 16, TOKENS)
    assert len(chunks) > 1
    assert all(c.tokens <= 512 for c in chunks)
    assert all(c.tokens == TOKENS.count(c.text) for c in chunks)


def test_chunk_keeps_table_rows_and_repeats_header() -> None:
    doc = document("# Grading\n| Grade | Points |\n| --- | --- |\n| A | 4 |\n| B | 3 |\n| C | 2 |")
    chunks = chunk(doc, 22, 0, TOKENS)
    table_chunks = [c for c in chunks if "| Grade | Points |" in c.text]
    assert len(table_chunks) >= 2
    assert all("| --- | --- |" in c.text for c in table_chunks)
    assert any("| A | 4 |" in c.text for c in table_chunks)
    assert any("| B | 3 |" in c.text for c in table_chunks)


def test_chunk_ids_stable_and_metadata_complete() -> None:
    doc = document("1 OCR\nA scanned rule with a source page.", ocr=True)
    first = chunk(doc, 50, 5, TOKENS)
    second = chunk(doc, 50, 5, TOKENS)
    assert [c.id for c in first] == [c.id for c in second]
    metadata = first[0].metadata()
    assert set(metadata) == {"source", "section", "page", "doc_version", "superseded", "ocr", "chunk_index", "tokens"}
    assert metadata["ocr"] is True and metadata["chunk_index"] == 0


def test_fixed_strategy_ignores_section_structure() -> None:
    doc = document("1 First\nOne body.\n\n2 Second\nAnother body.")
    chunks = chunk(doc, 50, 0, TOKENS, strategy="fixed")
    assert len(chunks) == 1
    assert chunks[0].section == "rules"
    assert "1 First" in chunks[0].text and "2 Second" in chunks[0].text
