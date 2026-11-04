"""Stage 1: Extract. PDF (or HTML, or Markdown) to text, page by page."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup

from .models import Document, Page


def _table_md(rows: list[list[str | None]]) -> str:
    clean = [[(cell or "").replace("\n", " ").strip() for cell in row] for row in rows]
    clean = [row for row in clean if any(row)]
    if not clean:
        return ""
    width = max(map(len, clean))
    clean = [row + [""] * (width - len(row)) for row in clean]
    return "\n".join(["| " + " | ".join(clean[0]) + " |",
                       "| " + " | ".join(["---"] * width) + " |",
                       *("| " + " | ".join(row) + " |" for row in clean[1:])])


def _pdf(path: Path, version: str, superseded: bool) -> Document:
    pages = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            tables = page.find_tables()
            pieces = []
            for table in tables:
                bbox = table.bbox
                body = page.crop((0, 0, page.width, bbox[1])).extract_text() or ""
                if body.strip():
                    pieces.append(body)
                rendered = _table_md(table.extract())
                if rendered:
                    pieces.append(rendered)
            if tables:
                last = max(t.bbox[3] for t in tables)
                tail = page.crop((0, last, page.width, page.height)).extract_text() or ""
                if tail.strip():
                    pieces.append(tail)
                text = "\n\n".join(pieces)
            else:
                text = page.extract_text() or ""
            ocr = False
            if len(re.sub(r"\s", "", text)) < 25 and os.getenv("OCR_ENABLED", "true").lower() not in {"false", "0", "no"}:
                try:
                    from pdf2image import convert_from_path
                    import pytesseract
                    if not shutil.which("tesseract"):
                        windows_tesseract = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
                        if windows_tesseract.is_file():
                            pytesseract.pytesseract.tesseract_cmd = str(windows_tesseract)
                    image = convert_from_path(str(path), dpi=300, first_page=number, last_page=number)[0]
                    text = pytesseract.image_to_string(image, lang="eng")
                    ocr = True
                except Exception as exc:
                    if os.getenv("OCR_REQUIRED", "false").lower() in {"true", "1", "yes"}:
                        raise RuntimeError(f"OCR failed for {path.name} page {number}: {exc}") from exc
            pages.append(Page(path.name, number, text, ocr))
    return Document(path.name, version, superseded, pages)


def _html(path: Path, version: str, superseded: bool) -> Document:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    for node in soup.select("script, style, nav, footer, header, noscript, aside"):
        node.decompose()
    main = soup.find("main") or soup.find(id=re.compile(r"content|main", re.I)) or soup.body or soup
    pieces = []
    for node in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "table"], recursive=True):
        if node.name.startswith("h"):
            level = int(node.name[1])
            pieces.append("#" * level + " " + node.get_text(" ", strip=True))
        elif node.name == "table":
            rows = [[cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"], recursive=False)]
                    for row in node.find_all("tr")]
            rendered = _table_md(rows)
            if rendered:
                pieces.append(rendered)
        else:
            value = node.get_text(" ", strip=True)
            if value:
                pieces.append(("- " if node.name == "li" else "") + value)
    return Document(path.name, version, superseded, [Page(path.name, 1, "\n\n".join(pieces))])


def extract(path: str, doc_version: str, superseded: bool) -> Document:
    """Return the document's text page by page.

    Detect pages with no text layer and OCR them; mark those pages ocr=True.
    The OCR libraries need system packages in your Dockerfile (tesseract-ocr,
    poppler-utils), not only pip packages.
    """
    file = Path(path)
    suffix = file.suffix.lower()
    if suffix == ".pdf":
        return _pdf(file, doc_version, superseded)
    if suffix in {".md", ".markdown", ".txt"}:
        text = file.read_text(encoding="utf-8", errors="replace")
        if suffix in {".md", ".markdown"} and text.startswith("---"):
            _, separator, rest = text[3:].partition("\n---")
            if separator:
                text = rest.lstrip("\r\n")
        return Document(file.name, doc_version, superseded, [Page(file.name, 1, text)])
    if suffix in {".html", ".htm"}:
        return _html(file, doc_version, superseded)
    raise ValueError(f"unsupported document type: {suffix or '<none>'}")
