"""Stage 1: Extract. PDF (or HTML, or Markdown) to text, page by page."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Sequence
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup

from .models import Document, Page


def _warn(msg: str, **fields: object) -> None:
    """One JSON log line on stdout, like pipeline.run.log (a pod's logs are its only record)."""
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "logger": "rahbar.indexer", "level": "WARNING", "msg": msg, **fields}),
          flush=True)


def _table_md(rows: Sequence[Sequence[str | None]]) -> str:
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
    skipped: list[int] = []   # pages with no text layer while OCR_ENABLED=false
    failed: list[int] = []    # pages where OCR raised
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            tables = sorted(page.find_tables(), key=lambda table: table.bbox[1])
            pieces = []
            cursor = 0.0
            for table in tables:
                top = min(page.height, max(cursor, table.bbox[1]))
                body = page.crop((0, cursor, page.width, top)).extract_text() or "" if top > cursor else ""
                if body.strip():
                    pieces.append(body)
                rendered = _table_md(table.extract())
                if rendered:
                    pieces.append(rendered)
                cursor = min(page.height, max(cursor, table.bbox[3]))
            if tables:
                tail = page.crop((0, cursor, page.width, page.height)).extract_text() or "" if cursor < page.height else ""
                if tail.strip():
                    pieces.append(tail)
                text = "\n\n".join(pieces)
            else:
                text = page.extract_text() or ""
            ocr = False
            if len(re.sub(r"\s", "", text)) < 25:           # no text layer on this page
                if os.getenv("OCR_ENABLED", "true").lower() in {"false", "0", "no"}:
                    skipped.append(number)                   # stage A switch (P5)
                else:
                    try:
                        from pdf2image import convert_from_path
                        import pytesseract
                        image = convert_from_path(str(path), dpi=300, first_page=number,
                                                  last_page=number)[0]
                        text = pytesseract.image_to_string(image, lang="eng")
                        ocr = True
                    except Exception as exc:                 # keep indexing, but say so
                        failed.append(number)
                        _warn("ocr failed, page left empty", source=path.name, page=number,
                              error=f"{type(exc).__name__}: {exc}")
            pages.append(Page(path.name, number, text, ocr))
    if skipped:
        _warn("pages without a text layer left empty because OCR is disabled",
              source=path.name, pages=len(skipped), first_pages=skipped[:5])
    if failed:
        _warn("pages left empty because OCR failed", source=path.name, pages=len(failed))
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
