"""Stage 2: Clean. Remove artefacts without destroying structure."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from .models import Document


def _key(line: str) -> str:
    value = unicodedata.normalize("NFKC", line).casefold()
    return re.sub(r"\d+", "#", " ".join(value.split()))


def clean(doc: Document) -> Document:
    """Strip headers and footers that repeat on every page; keep headings and
    section boundaries, because chunking and citations depend on them."""
    edge_pages: dict[str, set[int]] = defaultdict(set)
    lines_by_page: list[list[str]] = []
    for page in doc.pages:
        lines = [unicodedata.normalize("NFKC", line).rstrip() for line in page.text.splitlines()]
        lines_by_page.append(lines)
        for line in lines[:2] + (lines[-2:] if len(lines) > 2 else []):
            if line.strip():
                edge_pages[_key(line)].add(page.page)
    threshold = max(2, (len(doc.pages) + 1) // 2)
    repeated = {key for key, pages in edge_pages.items() if len(pages) >= threshold}
    for page, lines in zip(doc.pages, lines_by_page):
        kept = []
        for line in lines:
            if re.fullmatch(r"\s*(?:page\s+)?\d+(?:\s+of\s+\d+)?\s*", line, re.I):
                continue
            if line.strip() and _key(line) in repeated:
                continue
            kept.append(re.sub(r"[\t\u00a0 ]+", " ", line).strip())
        text = "\n".join(kept)
        text = re.sub(r"(?<=[A-Za-z])-[ \t]*\n[ \t]*(?=[a-z])", "", text)
        page.text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return doc
