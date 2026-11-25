"""Verify extracted documents after ingestion and before chunking (RAGOps paper 4.2.2).

Four checks per document, each with pass/fail and a reason:

- quality       empty, garbled or failed extraction, or too little text to be a document
- completeness  source, title, date/version and page count present; text not truncated
- recency       is a newer version of the same document (same doc_id) already known?
- uniqueness    exact duplicate (hash of the normalised text) or near-duplicate (embedding
                similarity) of another document in the lake or in this batch

Near-duplicate score: each document is embedded as up to 8 windows spread across its text.
For each window, take the best cosine against the other document's windows; average; take
the smaller of the two directions. Copies with small edits score ~0.99; different documents
on the same topic score below ~0.85 on this corpus (one averaged vector per document did not
separate them: every academic-rules document scored above 0.95).

Disposition: a quality, completeness or uniqueness failure sends the document to quarantine,
so it is never indexed. A recency failure means the document is an older version: it is
archived as `superseded` (indexed, but excluded from retrieval through metadata).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from .lake import version_key
from .models import Document

NEAR_DUPLICATE_THRESHOLD = 0.95
MIN_CHARACTERS = 200
MIN_ALNUM_RATIO = 0.45
WINDOW_CHARS = 1500
MAX_WINDOWS = 8
TERMINAL = tuple(".!?:;)]|\"'*`>")


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    reason: str


@dataclass
class Candidate:
    """One incoming document plus the metadata the verifier needs."""

    document: Document | None          # None when extraction failed
    source: str
    doc_id: str
    doc_version: str
    title: str
    file_type: str                     # pdf | html | md | txt
    declared_pages: int | None = None
    extraction_error: str = ""
    raw_tail: bytes = b""              # last bytes of the file (PDF %%EOF check)


@dataclass
class KnownDocument:
    """A document already in the lake (current or superseded)."""

    source: str
    doc_id: str
    doc_version: str
    status: str
    text_sha256: str
    embedding: list[list[float]]      # window vectors


@dataclass
class DocumentVerification:
    source: str
    checks: dict[str, CheckResult]
    text_sha256: str = ""
    embedding: list[list[float]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.checks.values())

    @property
    def disposition(self) -> str:
        blocking = [name for name in ("quality", "completeness", "uniqueness")
                    if not self.checks[name].passed]
        if blocking:
            return "quarantine"
        if not self.checks["recency"].passed:
            return "archive-superseded"
        return "accept"


def normalized_text(document: Document | None) -> str:
    if document is None:
        return ""
    return " ".join(" ".join(page.text.split()) for page in document.pages).strip()


def text_digest(text: str) -> str:
    return hashlib.sha256(text.casefold().encode("utf-8")).hexdigest()


def windows(text: str) -> list[str]:
    """Up to MAX_WINDOWS slices spread across the text, so a document vector reflects the
    whole document rather than only its first 512 tokens (its cover page)."""
    if len(text) <= WINDOW_CHARS:
        return [text] if text else []
    count = min(MAX_WINDOWS, math.ceil(len(text) / WINDOW_CHARS))
    step = (len(text) - WINDOW_CHARS) / max(count - 1, 1)
    return [text[int(i * step):int(i * step) + WINDOW_CHARS] for i in range(count)]


def document_vectors(text: str,
                     embed: Callable[[list[str]], list[list[float]]]) -> list[list[float]]:
    parts = windows(text)
    return [[round(value, 5) for value in vector] for vector in embed(parts)] if parts else []


def window_similarity(left: list[list[float]], right: list[list[float]]) -> float:
    """Symmetric mean best-window cosine (see the module docstring)."""
    if not left or not right:
        return 0.0
    forward = sum(max(cosine(a, b) for b in right) for a in left) / len(left)
    backward = sum(max(cosine(b, a) for a in left) for b in right) / len(right)
    return min(forward, backward)


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norms = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norms if norms else 0.0


def _quality(candidate: Candidate, text: str) -> CheckResult:
    if candidate.document is None:
        return CheckResult(False, f"extraction failed: {candidate.extraction_error}")
    if not text:
        return CheckResult(False, "extracted text is empty")
    ratio = sum(ch.isalnum() for ch in text) / max(len(text), 1)
    if ratio < MIN_ALNUM_RATIO:
        return CheckResult(False, f"extracted text appears garbled ({ratio:.0%} alphanumeric)")
    if len(text) < MIN_CHARACTERS:
        return CheckResult(False, f"extracted text is too short ({len(text)} characters)")
    return CheckResult(True, f"usable text ({len(text)} characters, {ratio:.0%} alphanumeric)")


def _completeness(candidate: Candidate) -> CheckResult:
    missing = []
    if not candidate.source.strip():
        missing.append("missing source")
    if not candidate.title.strip():
        missing.append("missing title")
    if not candidate.doc_version.strip() or candidate.doc_version == "unknown":
        missing.append("missing date/version")
    document = candidate.document
    pages = [page.page for page in document.pages] if document else []
    if not pages:
        missing.append("missing page count (no pages extracted)")
    elif pages != list(range(1, len(pages) + 1)):
        missing.append(f"page sequence has gaps {pages[:5]}...")
    if candidate.declared_pages and pages and len(pages) < candidate.declared_pages:
        missing.append(f"truncated: {len(pages)} of {candidate.declared_pages} declared pages")
    if candidate.file_type == "pdf" and candidate.raw_tail and b"%%EOF" not in candidate.raw_tail:
        missing.append("truncated: PDF file has no %%EOF end marker")
    if candidate.file_type in {"md", "txt"} and document and document.pages:
        tail = document.pages[-1].text.rstrip()
        if tail and not tail.endswith(TERMINAL):
            missing.append(f"truncated: text ends mid-sentence (...{tail[-40:]!r})")
    if missing:
        return CheckResult(False, "; ".join(missing))
    return CheckResult(True, f"source, title, version {candidate.doc_version} and "
                             f"{len(pages)} page(s) present; text complete")


def verify_documents(
    candidates: list[Candidate],
    *,
    known: list[KnownDocument] | None = None,
    embed: Callable[[list[str]], list[list[float]]] | None = None,
    near_duplicate_threshold: float = NEAR_DUPLICATE_THRESHOLD,
) -> list[DocumentVerification]:
    """Verify each candidate against the lake (`known`) and the earlier candidates.

    `embed` is the pinned model's embed function. Without it (offline unit tests) the
    near-duplicate check compares word shingles instead of embeddings.
    """
    known = known or []
    results: list[DocumentVerification] = []
    accepted: list[tuple[Candidate, DocumentVerification]] = []
    for candidate in candidates:
        text = normalized_text(candidate.document)
        digest = text_digest(text) if text else ""
        vector = document_vectors(text, embed) if (embed and text) else []
        checks = {"quality": _quality(candidate, text), "completeness": _completeness(candidate)}

        # recency: the newest other version of the same document, in the lake or this batch
        others = [(k.doc_version, k.source) for k in known
                  if k.doc_id == candidate.doc_id and k.source != candidate.source
                  and k.status != "deleted"]
        others += [(c.doc_version, c.source) for c in candidates
                   if c is not candidate and c.doc_id == candidate.doc_id
                   and c.source != candidate.source and c.document is not None]
        newer = sorted((o for o in others if version_key(o[0]) > version_key(
            candidate.doc_version)), key=lambda o: version_key(o[0]), reverse=True)
        if newer:
            checks["recency"] = CheckResult(
                False, f"newer version {newer[0][0]} detected ({newer[0][1]}); "
                       f"this version is archived as superseded")
        else:
            older = [o for o in others if version_key(o[0]) < version_key(candidate.doc_version)]
            note = f"; supersedes {', '.join(f'{s} {v}' for v, s in older)}" if older else ""
            checks["recency"] = CheckResult(True, f"no newer version of {candidate.doc_id}{note}")

        # uniqueness against the lake and the documents accepted earlier in this batch
        reasons = []

        def other_version(doc_id: str, version: str) -> bool:
            """A different version of the same document is a recency question, not a dupe."""
            return doc_id == candidate.doc_id and version != candidate.doc_version

        if digest:
            exact = next((k.source for k in known if k.text_sha256 == digest
                          and k.source != candidate.source and k.status != "deleted"
                          and not other_version(k.doc_id, k.doc_version)), None)
            exact = exact or next((c.source for c, r in accepted if r.text_sha256 == digest
                                   and not other_version(c.doc_id, c.doc_version)), None)
            if exact:
                reasons.append(f"exact duplicate of {exact} (same text hash {digest[:12]})")
            best_source, best_score = "", 0.0
            pool = [(k.source, k.doc_id, k.doc_version, k.embedding, k.status) for k in known
                    if k.source != candidate.source]
            pool += [(c.source, c.doc_id, c.doc_version, r.embedding, "batch")
                     for c, r in accepted]
            for source, doc_id, version, other_vector, status in pool:
                if other_version(doc_id, version) or status == "deleted":
                    continue
                if vector and other_vector:
                    score = window_similarity(vector, other_vector)
                else:
                    other_text = next((normalized_text(c.document) for c, _ in accepted
                                       if c.source == source), "")
                    score = _shingle_similarity(text, other_text)
                if score > best_score:
                    best_source, best_score = source, score
            if not exact and best_score >= near_duplicate_threshold:
                reasons.append(f"near-duplicate of {best_source} "
                               f"(similarity {best_score:.3f} >= {near_duplicate_threshold})")
            closest = f"; closest other document {best_source} at {best_score:.3f}" \
                if best_source else ""
        else:
            closest = ""
        checks["uniqueness"] = CheckResult(
            not reasons, "; ".join(reasons) or f"no exact or near duplicate{closest}")

        result = DocumentVerification(candidate.source, checks, digest, vector)
        results.append(result)
        if result.disposition != "quarantine":
            accepted.append((candidate, result))
    return results


def _shingle_similarity(left: str, right: str, size: int = 5) -> float:
    def shingles(text: str) -> set[str]:
        words = re.findall(r"\w+", text.casefold())
        return {" ".join(words[i:i + size]) for i in range(max(len(words) - size + 1, 1))}
    a, b = shingles(left), shingles(right)
    return len(a & b) / len(a | b) if a and b else 0.0
