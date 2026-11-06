"""Structure-aware chunking with a per-section token overlap."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .models import Chunk, Document
from .tokens import TokenCounter, count_tokens

MAX_EMBED_TOKENS = 512
_NUMBERED = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+\S")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'([{])")
_TABLE_RULE = re.compile(r"^\|\s*:?-{3,}")


@dataclass
class _Unit:
    text: str
    page: int
    ocr: bool


@dataclass
class _Section:
    heading: str
    page: int
    units: list[_Unit] = field(default_factory=list)


def _heading(line: str, markdown: bool = False) -> str | None:
    value = line.strip()
    if value.startswith("#"):
        return value.lstrip("# ").strip() or None
    # Markdown marks its headings with '#'. A numbered line there is a clause of body text
    # ("1.1 A student must attend ..."); treating it as a heading left its section empty, and
    # empty sections are dropped, so the clause was lost. PDFs and HTML keep the rules below.
    if markdown:
        return None
    if _NUMBERED.match(value):
        return value
    letters = [char for char in value if char.isalpha()]
    if 3 <= len(value) <= 90 and len(letters) >= 3 and value == value.upper():
        return value
    return None


def _slug(source: str) -> str:
    stem = Path(source).stem.casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return slug or "document"


def _hard_split(text: str, limit: int, counter: TokenCounter) -> list[str]:
    if count_tokens(text, counter) <= limit:
        return [text]
    words = text.split()
    output: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if count_tokens(candidate, counter) <= limit:
            current = candidate
            continue
        if current:
            output.append(current)
            current = ""
        if count_tokens(word, counter) <= limit:
            current = word
            continue
        fragment = ""
        for char in word:
            if count_tokens(fragment + char, counter) > limit and fragment:
                output.append(fragment)
                fragment = ""
            fragment += char
        current = fragment
    if current:
        output.append(current)
    return output


def _table_pieces(text: str, limit: int, counter: TokenCounter) -> list[str]:
    rows = [line for line in text.splitlines() if line.strip()]
    if count_tokens(text, counter) <= limit:
        return [text]
    header_count = 2 if len(rows) > 1 and _TABLE_RULE.match(rows[1]) else 1
    header = rows[:header_count]
    pieces: list[str] = []
    current = header[:]
    for row in rows[header_count:]:
        candidate = "\n".join([*current, row])
        if count_tokens(candidate, counter) <= limit:
            current.append(row)
            continue
        if len(current) > header_count:
            pieces.append("\n".join(current))
        row_with_header = "\n".join([*header, row])
        if count_tokens(row_with_header, counter) <= limit:
            current = [*header, row]
        else:
            pieces.extend(_hard_split(row_with_header, limit, counter))
            current = header[:]
    if len(current) > header_count:
        pieces.append("\n".join(current))
    return pieces or _hard_split(text, limit, counter)


def _atoms(unit: _Unit, limit: int, counter: TokenCounter) -> list[_Unit]:
    if unit.text.lstrip().startswith("|"):
        return [_Unit(piece, unit.page, unit.ocr) for piece in _table_pieces(unit.text, limit, counter)]
    sentences = [part.strip() for part in _SENTENCE.split(unit.text.strip()) if part.strip()]
    pieces: list[_Unit] = []
    for sentence in sentences or [unit.text.strip()]:
        pieces.extend(_Unit(part, unit.page, unit.ocr) for part in _hard_split(sentence, limit, counter))
    return pieces


def _sections(doc: Document) -> list[_Section]:
    fallback = Path(doc.source).stem.replace("_", " ") or doc.source
    markdown = Path(doc.source).suffix.lower() in {".md", ".markdown"}
    sections = [_Section(fallback, doc.pages[0].page if doc.pages else 1)]
    paragraph: list[str] = []
    paragraph_page = sections[0].page
    paragraph_ocr = False
    table: list[str] = []
    table_page = sections[0].page
    table_ocr = False

    def flush_paragraph() -> None:
        nonlocal paragraph, paragraph_ocr
        if paragraph:
            sections[-1].units.append(_Unit(" ".join(line.strip() for line in paragraph), paragraph_page, paragraph_ocr))
            paragraph = []
            paragraph_ocr = False

    def flush_table() -> None:
        nonlocal table, table_ocr
        if table:
            sections[-1].units.append(_Unit("\n".join(table), table_page, table_ocr))
            table = []
            table_ocr = False

    for page in doc.pages:
        for line in page.text.splitlines():
            if not line.strip():
                flush_paragraph()
                flush_table()
                continue
            title = _heading(line, markdown)
            if title:
                flush_paragraph()
                flush_table()
                sections.append(_Section(title, page.page))
                continue
            if line.strip().startswith("|") and line.strip().endswith("|"):
                flush_paragraph()
                if not table:
                    table_page, table_ocr = page.page, page.ocr
                table.append(line.strip())
                table_ocr = table_ocr or page.ocr
            else:
                flush_table()
                if not paragraph:
                    paragraph_page, paragraph_ocr = page.page, page.ocr
                paragraph.append(line)
                paragraph_ocr = paragraph_ocr or page.ocr
        flush_paragraph()
        flush_table()
    return [section for section in sections if section.units]


def _overlap(text: str, count: int, counter: TokenCounter) -> str:
    if count <= 0 or not text:
        return ""
    words = text.split()
    selected: list[str] = []
    for word in reversed(words):
        candidate = " ".join([word, *reversed(selected)])
        if count_tokens(candidate, counter) > count:
            break
        selected.append(word)
    return " ".join(reversed(selected))


def chunk(
    doc: Document,
    size: int,
    overlap: int,
    tokenizer: TokenCounter | None = None,
    strategy: str | None = None,
) -> list[Chunk]:
    """Split section, paragraph, sentence, then token, keeping metadata on every chunk.

    A tokenizer can be injected in tests. Production uses the cached FastEmbed tokenizer.
    ``fixed`` is the low-cost failure-stage switch and deliberately skips heading detection.
    """
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError("size must be positive and overlap must be between zero and size")
    counter = tokenizer
    if counter is None:
        from .tokens import get_tokenizer

        counter = get_tokenizer()
    limit = min(size, MAX_EMBED_TOKENS)
    mode = strategy or os.environ.get("CHUNK_STRATEGY", "structure")
    if mode not in {"structure", "fixed"}:
        raise ValueError(f"unsupported CHUNK_STRATEGY {mode!r}")

    if mode == "fixed":
        sections = [_Section(Path(doc.source).stem.replace("_", " ") or doc.source, doc.pages[0].page if doc.pages else 1)]
        for page in doc.pages:
            if page.text.strip():
                sections[0].units.append(_Unit(page.text.strip(), page.page, page.ocr))
    else:
        sections = _sections(doc)

    results: list[Chunk] = []
    source_slug = _slug(doc.source)
    for section in sections:
        heading = section.heading or doc.source
        heading_cost = count_tokens(heading, counter) + 1
        body_limit = limit - heading_cost
        if body_limit < 1:
            raise ValueError(f"section heading is too long for the {limit}-token chunk limit")
        current = ""
        current_page = section.page
        current_ocr = False

        def emit(body: str, page: int, ocr: bool) -> None:
            text = f"{heading}\n{body}" if body else heading
            token_count = count_tokens(text, counter)
            if token_count > limit:
                raise ValueError(f"chunk has {token_count} tokens, exceeding the {limit}-token limit")
            results.append(Chunk(
                id=f"{source_slug}:{len(results):05d}", text=text, source=doc.source,
                section=heading, page=page, doc_version=doc.doc_version,
                superseded=doc.superseded, ocr=ocr, chunk_index=len(results), tokens=token_count,
            ))

        for unit in section.units:
            for atom in _atoms(unit, body_limit, counter):
                if not current:
                    current, current_page, current_ocr = atom.text, atom.page, atom.ocr
                    continue
                candidate = f"{current}\n{atom.text}"
                if count_tokens(f"{heading}\n{candidate}", counter) <= limit:
                    current = candidate
                    current_ocr = current_ocr or atom.ocr
                    continue
                emit(current, current_page, current_ocr)
                tail = _overlap(current, overlap, counter)
                next_body = f"{tail}\n{atom.text}" if tail else atom.text
                while tail and count_tokens(f"{heading}\n{next_body}", counter) > limit:
                    tail = _overlap(tail, max(0, count_tokens(tail, counter) - 1), counter)
                    next_body = f"{tail}\n{atom.text}" if tail else atom.text
                current = next_body
                current_page = atom.page
                current_ocr = current_ocr or atom.ocr
        if current:
            emit(current, current_page, current_ocr)
    return results
