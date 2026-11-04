from pipeline.clean import clean
from pipeline.models import Document, Page


def test_clean_strips_repeating_header_keeps_heading() -> None:
    doc = Document("rules.pdf", "2026", False, [
        Page("rules.pdf", 1, "FAST-NUCES 2026\n1.1 Attendance\nStudents must attend.\n1"),
        Page("rules.pdf", 2, "FAST-NUCES 2026\n1.2 Grading\nA grade is awarded.\n2"),
    ])
    cleaned = clean(doc)
    assert "FAST-NUCES" not in cleaned.pages[0].text
    assert "1.1 Attendance" in cleaned.pages[0].text
    assert "1.2 Grading" in cleaned.pages[1].text
    assert "\n1" not in cleaned.pages[0].text


def test_clean_joins_hyphenation_but_preserves_lines_and_table_pipes() -> None:
    doc = Document("x.pdf", "v", False, [Page("x.pdf", 1, "inter-\nnational\n| A | B |\n2")])
    text = clean(doc).pages[0].text
    assert "international" in text
    assert "| A | B |" in text
