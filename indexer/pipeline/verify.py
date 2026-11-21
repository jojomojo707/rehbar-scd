"""Verify extracted documents before chunking or indexing."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable

from .models import Document

NEAR_DUPLICATE_THRESHOLD = 0.92


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    reason: str


@dataclass(frozen=True)
class DocumentVerification:
    source: str
    checks: dict[str, CheckResult]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.checks.values())


def _normalized_text(document: Document) -> str:
    return " ".join(" ".join(page.text.split()) for page in document.pages).strip()


def _version_key(version: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", version)
    return tuple(int(number) for number in numbers) or (0,)


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def verify_documents(
    documents: list[Document],
    *,
    existing: list[Document] | None = None,
    embed: Callable[[list[str]], list[list[float]]] | None = None,
    near_duplicate_threshold: float = NEAR_DUPLICATE_THRESHOLD,
) -> list[DocumentVerification]:
    """Return four per-document checks; no document is modified or indexed here.

    Supply the pinned model's ``embed`` function to detect semantic near-duplicates.
    A deterministic text-similarity fallback keeps local verification tests offline.
    """
    existing = existing or []
    corpus = existing + documents
    texts = [_normalized_text(document) for document in corpus]
    vectors = embed(texts) if embed and texts else []
    results: list[DocumentVerification] = []
    seen_hashes: dict[str, str] = {}
    for index, document in enumerate(corpus):
        text = texts[index]
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        seen_hashes[digest] = document.source

    for index, document in enumerate(documents, start=len(existing)):
        text = texts[index]
        quality_reasons = []
        if not text:
            quality_reasons.append("extracted text is empty")
        elif sum(char.isalnum() for char in text) / max(len(text), 1) < 0.45:
            quality_reasons.append("extracted text appears garbled")
        elif len(text) < 40:
            quality_reasons.append(f"extracted text is too short ({len(text)} characters)")

        missing = []
        if not document.source.strip():
            missing.append("source")
        if not document.source.strip():
            missing.append("title")
        if not document.doc_version.strip() or document.doc_version == "unknown":
            missing.append("date/version")
        if not document.pages or any(page.page < 1 for page in document.pages):
            missing.append("page count")
        if document.pages and [p.page for p in document.pages] != list(
            range(1, len(document.pages) + 1)
        ):
            missing.append("complete page sequence")

        newer = [old for old in existing if old.source == document.source
                 and _version_key(old.doc_version) > _version_key(document.doc_version)]

        duplicate_source = next((other.source for other in corpus[:index] if
                                 hashlib.sha256(_normalized_text(other).encode()).digest() ==
                                 hashlib.sha256(text.encode()).digest()), None)
        near_source = None
        near_score = 0.0
        for previous_index, previous in enumerate(corpus[:index]):
            if previous.source == document.source:
                continue
            if vectors:
                score = _cosine(vectors[index], vectors[previous_index])
            else:
                score = SequenceMatcher(None, text.casefold(),
                                        texts[previous_index].casefold()).ratio()
            if score > near_score:
                near_source, near_score = previous.source, score

        uniqueness_reasons = []
        if duplicate_source:
            uniqueness_reasons.append(f"exact duplicate of {duplicate_source}")
        if near_source and near_score >= near_duplicate_threshold:
            uniqueness_reasons.append(
                f"near-duplicate of {near_source} (similarity {near_score:.3f})")

        checks = {
            "quality": CheckResult(not quality_reasons, "; ".join(quality_reasons) or
                                   "extracted text is usable"),
            "completeness": CheckResult(not missing, "; ".join(
                f"missing or invalid {item}" for item in missing) or
                "source, title, version and page sequence are present"),
            "recency": CheckResult(not newer, (f"newer version {newer[0].doc_version} exists"
                                   if newer else "no newer version of this document exists")),
            "uniqueness": CheckResult(not uniqueness_reasons, "; ".join(uniqueness_reasons) or
                                      "no exact or near-duplicate found"),
        }
        results.append(DocumentVerification(document.source, checks))
    return results
