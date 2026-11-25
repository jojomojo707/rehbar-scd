"""The data lake on the pipeline-data PVC (RAGOps paper, section 4.2.3).

Layout under PIPELINE_DATA_DIR:

    inbox/<run_id>/<file>                 staged copy of a new or changed source, before verify
    quarantine/<run_id>/<file>            sources that failed verification (moved from inbox)
    lake/docs/<file>                      the current, verified version of every document
    lake/manifest.json                    one entry per source file: version, status, digest...
    archive/<doc_id>/<version>/<file>     superseded, replaced and deleted versions (+ meta.json)

The manifest is the record of what the lake holds. Its `status` is `current`, `superseded`
(kept in the index but filtered out of retrieval through metadata) or `deleted` (archived only,
not indexed). Nothing here talks to Chroma: the indexer builds the collection from the manifest.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def version_key(version: str) -> tuple[int, ...]:
    """Order versions such as 2023-08 < 2026-06 < 2027 by their numbers."""
    numbers = re.findall(r"\d+", version or "")
    return tuple(int(number) for number in numbers) or (0,)


def default_doc_id(source: str) -> str:
    """A document's identity when its metadata gives none: the file name without years."""
    stem = source.rsplit("/", 1)[-1].rsplit(".", 1)[0].casefold()
    return re.sub(r"[-_ ]?20\d{2}(?:[-_]\d{2})?", "", stem).strip("-_ ") or stem


@dataclass
class LakeEntry:
    source: str                 # file name; also the chunk metadata `source`
    doc_id: str                 # identity shared by every version of one document
    doc_version: str
    title: str
    sha256: str                 # digest of the source file bytes
    text_sha256: str            # digest of the normalised extracted text (exact duplicates)
    origin: str                 # "corpus" or the batch name it arrived in
    status: str                 # current | superseded | deleted
    path: str                   # where the file lives now (lake/docs or archive/...)
    ingested_at: str
    run_id: str
    pinned: bool = False        # set by a restore: keep this version current
    embedding: list[list[float]] = field(default_factory=list)  # window vectors (near-dupes)
    history: list[dict[str, str]] = field(default_factory=list)


class DataLake:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.docs = self.root / "lake" / "docs"
        self.manifest_path = self.root / "lake" / "manifest.json"
        self.archive_root = self.root / "archive"
        self.quarantine_root = self.root / "quarantine"
        self.inbox_root = self.root / "inbox"
        self.entries: dict[str, LakeEntry] = {}
        # Quarantined sources by file name: the digest that failed, the run and the reasons.
        # An unchanged quarantined file is not re-verified (or accepted) on later runs.
        self.registry_path = self.root / "lake" / "quarantine-registry.json"
        self.quarantined: dict[str, dict[str, object]] = (
            json.loads(self.registry_path.read_text(encoding="utf-8"))
            if self.registry_path.exists() else {})
        if self.manifest_path.exists():
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            self.entries = {key: LakeEntry(**value) for key, value in raw.items()}

    # ----- queries -------------------------------------------------------------------------
    def indexed(self) -> list[LakeEntry]:
        """Entries that belong in the collection: current and superseded versions."""
        return sorted((e for e in self.entries.values() if e.status != "deleted"),
                      key=lambda e: e.source)

    def current_for(self, doc_id: str) -> list[LakeEntry]:
        return [e for e in self.entries.values() if e.doc_id == doc_id and e.status == "current"]

    # ----- file movements ------------------------------------------------------------------
    def stage(self, source_path: Path, run_id: str) -> Path:
        """Copy an incoming source into the run's inbox (inputs are read-only mounts)."""
        target = self.inbox_root / run_id / source_path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        return target

    def quarantine(self, staged: Path, run_id: str, reasons: dict[str, str],
                   digest: str = "") -> Path:
        target = self.quarantine_root / run_id / staged.name
        self.quarantined[staged.name] = {"sha256": digest, "run_id": run_id,
                                         "failed_checks": reasons, "path": str(target)}
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), target)
        (target.parent / f"{staged.name}.reason.json").write_text(
            json.dumps({"source": staged.name, "run_id": run_id, "failed_checks": reasons,
                        "quarantined_at": now()}, indent=2) + "\n", encoding="utf-8")
        return target

    def _archive_file(self, entry: LakeEntry, reason: str) -> None:
        current = Path(entry.path)
        target = self.archive_root / entry.doc_id / _safe(entry.doc_version) / entry.source
        if current.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            if current.exists():
                shutil.move(str(current), target)
            entry.path = str(target)
        meta = {k: v for k, v in asdict(entry).items() if k != "embedding"}
        (target.parent / f"{entry.source}.meta.json").write_text(
            json.dumps({**meta, "archived_reason": reason, "archived_at": now()}, indent=2)
            + "\n", encoding="utf-8")

    def accept(self, staged: Path, entry: LakeEntry) -> list[str]:
        """Move a verified source into lake/docs; archive the version it replaces."""
        actions = []
        old = self.entries.get(entry.source)
        if old is not None and old.sha256 != entry.sha256:
            replaced = LakeEntry(**asdict(old))
            replaced.source = old.source
            self._archive_file(replaced, f"replaced by {entry.doc_version} ({entry.sha256[:8]})")
            actions.append(f"archived replaced {old.source} {old.doc_version}")
            entry.history = [*old.history, {"version": old.doc_version, "sha256": old.sha256,
                                            "archived_to": replaced.path, "at": now()}]
        self.quarantined.pop(entry.source, None)
        target = self.docs / entry.source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), target)
        entry.path = str(target)
        self.entries[entry.source] = entry
        actions.append(f"moved {entry.source} into the lake")
        return actions

    def apply_recency(self) -> list[str]:
        """Per doc_id, keep the newest (or a pinned) version current; archive the others."""
        actions = []
        by_doc: dict[str, list[LakeEntry]] = {}
        for entry in self.entries.values():
            if entry.status != "deleted":
                by_doc.setdefault(entry.doc_id, []).append(entry)
        for doc_id, versions in by_doc.items():
            pinned = [e for e in versions if e.pinned]
            keep = pinned[0] if pinned else max(versions, key=lambda e: version_key(e.doc_version))
            for entry in versions:
                if entry is keep:
                    if entry.status != "current":
                        entry.status = "current"
                        self._unarchive(entry)
                        actions.append(f"{entry.source} {entry.doc_version} is current again")
                elif entry.status != "superseded":
                    entry.status = "superseded"
                    self._archive_file(entry, f"superseded by {keep.source} {keep.doc_version}")
                    actions.append(f"archived superseded {entry.source} {entry.doc_version} "
                                   f"(newer: {keep.source} {keep.doc_version}) [{doc_id}]")
        return actions

    def _unarchive(self, entry: LakeEntry) -> None:
        source = Path(entry.path)
        target = self.docs / entry.source
        if source.exists() and source.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)   # the archive keeps its copy as the audit record
            entry.path = str(target)

    def delete(self, source: str, reason: str) -> str:
        entry = self.entries[source]
        entry.status = "deleted"
        entry.pinned = False
        self._archive_file(entry, reason)
        return f"archived deleted {source} {entry.doc_version} ({reason})"

    def restore(self, source: str, version: str | None = None) -> str:
        """Bring an archived (superseded or deleted) version back as the current one."""
        entry = self.entries.get(source)
        if entry is None:
            raise ValueError(f"{source} is not in the lake manifest")
        if version and entry.doc_version != version:
            raise ValueError(f"{source} has version {entry.doc_version}, not {version}")
        if entry.status == "current":
            raise ValueError(f"{source} {entry.doc_version} is already current")
        for other in self.entries.values():
            if other.doc_id == entry.doc_id:
                other.pinned = False
        if entry.status == "deleted" and entry.origin == "corpus":
            entry.origin = "restored"   # no longer mirrors the corpus, so sync won't re-delete
        entry.pinned = True
        entry.status = "superseded"   # apply_recency makes the pinned entry current
        actions = self.apply_recency()
        return "; ".join([f"restored {source} {entry.doc_version}", *actions])

    def save(self) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {key: asdict(value) for key, value in sorted(self.entries.items())}
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        tmp.replace(self.manifest_path)
        self.registry_path.write_text(json.dumps(self.quarantined, indent=1, sort_keys=True)
                                      + "\n", encoding="utf-8")


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text or "unknown")
