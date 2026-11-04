from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from pipeline.extract import extract


def pdf(path: Path, pages: list[str]) -> None:
    doc = canvas.Canvas(str(path), pagesize=letter)
    for text in pages:
        if text:
            doc.drawString(72, 720, text)
        doc.showPage()
    doc.save()


def test_extract_markdown_front_matter(tmp_path: Path) -> None:
    file = tmp_path / "sample.md"
    file.write_text("---\ndoc_version: 2026\n---\n# 1 Rule\nA fact.", encoding="utf-8")
    doc = extract(str(file), "2026", False)
    assert doc.pages[0].text == "# 1 Rule\nA fact."
    assert doc.pages[0].page == 1


def test_extract_pdf_text_and_page_numbers(tmp_path: Path) -> None:
    file = tmp_path / "sample.pdf"
    pdf(file, ["Clause 1.1. Real text on this page.", "Second page has text."])
    doc = extract(str(file), "2026", False)
    assert [p.page for p in doc.pages] == [1, 2]
    assert "Clause 1.1" in doc.pages[0].text


def test_extract_pdf_table_markdown(tmp_path: Path) -> None:
    file = tmp_path / "table.pdf"
    doc = canvas.Canvas(str(file), pagesize=letter)
    for y in (720, 700, 680):
        doc.line(72, y, 220, y)
    for x in (72, 145, 220):
        doc.line(x, 680, x, 720)
    doc.drawString(78, 706, "Grade")
    doc.drawString(151, 706, "Points")
    doc.drawString(78, 686, "A-")
    doc.drawString(151, 686, "3.67")
    doc.save()
    result = extract(str(file), "2026", False)
    assert "| Grade | Points |" in result.pages[0].text
    assert "| A- | 3.67 |" in result.pages[0].text


def test_extract_html_main_and_table(tmp_path: Path) -> None:
    file = tmp_path / "fees.html"
    file.write_text("<nav>ignore nav</nav><main><h1>Fees</h1><table><tr><th>Item</th><th>Cost</th></tr><tr><td>Tuition</td><td>10</td></tr></table></main><footer>ignore</footer>", encoding="utf-8")
    text = extract(str(file), "2026", False).pages[0].text
    assert "# Fees" in text and "| Tuition | 10 |" in text
    assert "ignore" not in text


@pytest.mark.skipif(not (__import__("shutil").which("tesseract") or Path("C:/Program Files/Tesseract-OCR/tesseract.exe").is_file()), reason="Tesseract is not installed")
def test_ocr_page_detected(tmp_path: Path) -> None:
    file = tmp_path / "image.pdf"
    pdf(file, [""])
    result = extract(str(file), "2026", False)
    assert result.pages[0].page == 1 and result.pages[0].ocr is True


def test_ocr_disabled_does_not_call_ocr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "image.pdf"
    pdf(file, [""])
    monkeypatch.setenv("OCR_ENABLED", "false")
    assert extract(str(file), "2026", False).pages[0].ocr is False
