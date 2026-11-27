"""The indexer Job's entry point. It runs once and exits (section 4.2).

    python -m pipeline.run                         # ingest CORPUS_DIR (+ BATCH_DIR and
                                                   # PIPELINE_DATA_DIR/incoming/<batch>/) and index
    python -m pipeline.run --batch-dir DIR         # also ingest an extra batch of documents
    python -m pipeline.run --restore-version SRC   # make an archived version current again
    python -m pipeline.run --delete SRC            # archive a document and drop its chunks
    python -m pipeline.run --restore               # point the active alias at the previous index
    python -m pipeline.run --dummy                 # three fake chunks, no model needed

The data lifecycle follows the RAGOps paper (Figure 3): ingest (stage new or changed sources
into the inbox), verify (four checks per document), update the data lake (quarantine, accept,
archive superseded/replaced/deleted versions) and update the retrieval sources (re-chunk and
re-embed only what changed, then publish a new collection version).

Exit code 0 means the run completed, even when some documents were quarantined; the
verification report lists them. Anything else fails the Job.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import IndexerSettings, get_settings
from .lake import DataLake, LakeEntry, default_doc_id, sha256_file
from .models import Chunk, Document
from .tokens import get_tokenizer

SUPPORTED = {".pdf", ".md", ".markdown", ".html", ".htm", ".txt"}


def log(msg: str, **fields: object) -> None:
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "logger": "rahbar.indexer", "msg": msg, **fields}), flush=True)


@dataclass
class SourceDoc:
    path: Path
    source: str
    doc_version: str
    doc_id: str
    title: str
    declared_pages: int | None
    origin: str


def _front_matter(path: Path) -> dict[str, str]:
    """Read `key: value` lines between leading '---' markers."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return meta


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def discover(directory: str, origin: str = "corpus") -> list[SourceDoc]:
    """List every document in a directory with its metadata.

    corpus/fetch.py writes _index.json next to the files it downloads; use it when present.
    Otherwise read Markdown front matter (batches and CI fixtures work this way). A file with
    no metadata still appears: verification then fails it on completeness.
    """
    root = Path(directory)
    index = root / "_index.json"
    found = []
    if index.exists():
        entries = json.loads(index.read_text(encoding="utf-8"))
        found = [SourceDoc(root / e["file"], e["file"], str(e.get("doc_version", "unknown")),
                           str(e.get("doc_id") or default_doc_id(e["file"])),
                           str(e.get("title") or e.get("name") or ""),
                           _int_or_none(e.get("pages")), origin)
                 for e in entries]
        if origin == "corpus":
            return found          # fetch.py's index is the complete list for the corpus
    listed = {doc.source for doc in found}
    # In a batch, files that _index.json does not list are still verified (not silently
    # skipped): with no title or version they fail completeness and are quarantined.
    for path in sorted(root.glob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED or path.name in listed:
            continue
        if path.name.lower().startswith("readme") or path.name.startswith("_"):
            continue
        meta = _front_matter(path) if path.suffix.lower() in {".md", ".markdown"} else {}
        found.append(SourceDoc(path, path.name, meta.get("doc_version", "unknown"),
                               meta.get("doc_id") or default_doc_id(path.name),
                               meta.get("title", ""), _int_or_none(meta.get("pages")), origin))
    return found


def _raw_tail(path: Path) -> bytes:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        handle.seek(max(handle.tell() - 2048, 0))
        return handle.read()


def _file_type(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return {"markdown": "md", "htm": "html"}.get(suffix, suffix)


def _metadata(doc: SourceDoc) -> dict[str, str]:
    """The operator-supplied metadata the completeness and recency checks read."""
    return {"doc_id": doc.doc_id, "doc_version": doc.doc_version, "title": doc.title}


def ingest_and_verify(
    settings: IndexerSettings, lake: DataLake, run_id: str, sources: list[SourceDoc],
    corpus_sources: set[str] | None,
) -> dict[str, Any]:
    """Stages 1-3 of Figure 3: ingest into the inbox, verify, update the data lake."""
    from .embed import embed
    from .extract import extract
    from .verify import Candidate, KnownDocument, verify_documents

    unchanged, incoming, held = [], [], []
    for doc in sources:
        digest = sha256_file(doc.path)
        entry = lake.entries.get(doc.source)
        failed_before = lake.quarantined.get(doc.source, {})
        if (failed_before.get("sha256") == digest
                and failed_before.get("metadata", _metadata(doc)) == _metadata(doc)):
            held.append(doc.source)   # same bytes and metadata that failed before: still held
        elif entry is not None and entry.sha256 == digest:
            # unchanged; a deleted document stays deleted until its file changes or an
            # operator restores it with --restore-version
            unchanged.append(doc.source)
        else:
            incoming.append((doc, digest, "changed" if entry and entry.status != "deleted"
                             else "new"))

    actions: list[str] = []
    if corpus_sources is not None:
        for entry in list(lake.entries.values()):
            if (entry.origin == "corpus" and entry.status != "deleted"
                    and entry.source not in corpus_sources):
                actions.append(lake.delete(entry.source, "removed from the corpus"))

    candidates, staged = [], {}
    for doc, _digest, _kind in incoming:
        path = lake.stage(doc.path, run_id)
        staged[doc.source] = path
        try:
            document: Document | None = extract(str(path), doc.doc_version, False)
            error = ""
        except Exception as exc:   # corrupt files are a verification result, not a crash
            document, error = None, f"{type(exc).__name__}: {exc}"
        candidates.append(Candidate(document, doc.source, doc.doc_id, doc.doc_version,
                                    doc.title, _file_type(path), doc.declared_pages, error,
                                    _raw_tail(path) if path.suffix.lower() == ".pdf" else b""))
    incoming_names = {doc.source for doc, _d, _k in incoming}
    known = [KnownDocument(e.source, e.doc_id, e.doc_version, e.status, e.text_sha256,
                           e.embedding)
             for e in lake.entries.values() if e.source not in incoming_names]
    results = verify_documents(candidates, known=known,
                               embed=lambda texts: embed(texts, settings)) if candidates else []

    records = []
    extracted: dict[str, Document] = {}
    for (doc, digest, kind), candidate, result in zip(incoming, candidates, results):
        disposition = result.disposition
        record: dict[str, Any] = {
            "source": doc.source, "doc_id": doc.doc_id, "doc_version": doc.doc_version,
            "title": doc.title, "origin": doc.origin, "change": kind, "sha256": digest,
            "passed": result.passed, "disposition": disposition,
            "checks": {name: {"passed": check.passed, "reason": check.reason}
                       for name, check in result.checks.items()},
        }
        if disposition == "quarantine":
            failed = {n: c.reason for n, c in result.checks.items() if not c.passed}
            record["moved_to"] = str(lake.quarantine(staged[doc.source], run_id, failed,
                                                     digest, _metadata(doc)))
        else:
            entry = LakeEntry(doc.source, doc.doc_id, doc.doc_version, doc.title, digest,
                              result.text_sha256, doc.origin, "current", "",
                              datetime.now(UTC).isoformat(timespec="seconds"), run_id,
                              embedding=result.embedding)
            actions += lake.accept(staged[doc.source], entry)
            record["moved_to"] = entry.path
            if candidate.document is not None:
                extracted[doc.source] = candidate.document
        records.append(record)
    actions += lake.apply_recency()
    for record in records:
        entry = lake.entries.get(record["source"])
        if entry is not None and record["disposition"] != "quarantine":
            record["lake_status"] = entry.status
            record["moved_to"] = entry.path
    lake.save()
    try:
        (lake.inbox_root / run_id).rmdir()
    except OSError:
        pass
    return {"records": records, "unchanged": unchanged, "lake_actions": actions,
            "extracted": extracted, "still_quarantined": held}


def _chunks_from_snapshot(rows: list[dict[str, Any]], entry: LakeEntry) -> list[Chunk]:
    chunks = []
    for row in sorted(rows, key=lambda r: int(r["metadata"].get("chunk_index", 0))):
        meta = row["metadata"]
        chunks.append(Chunk(id=row["id"], text=row["document"], source=entry.source,
                            section=str(meta.get("section", "")), page=int(meta.get("page", 1)),
                            doc_version=entry.doc_version,
                            superseded=entry.status == "superseded",
                            ocr=bool(meta.get("ocr", False)),
                            chunk_index=int(meta.get("chunk_index", 0)),
                            tokens=int(meta.get("tokens", 0))))
    return chunks


def update_retrieval_sources(
    settings: IndexerSettings, lake: DataLake, extracted: dict[str, Document],
) -> dict[str, Any]:
    """Stage 4 of Figure 3: re-chunk and re-embed only new or changed documents."""
    from .chunk import chunk
    from .clean import clean
    from .embed import embed
    from .extract import extract
    from .store import active_snapshot, get_client, plan_incremental, store

    entries = lake.indexed()
    if not entries:
        raise ValueError("the data lake holds no indexable document")
    client = get_client(settings)
    snapshot = active_snapshot(settings, client)
    meta = snapshot.get("metadata", {})
    compatible = (meta.get("embed_model") == settings.embed_model
                  and meta.get("chunk_size") == settings.chunk_size
                  and meta.get("chunk_overlap") == settings.chunk_overlap
                  and meta.get("chunk_strategy") == settings.chunk_strategy)
    rows_by_source: dict[str, list[dict[str, Any]]] = {}
    for identifier, record in snapshot.get("records", {}).items():
        rows_by_source.setdefault(str(record["metadata"].get("source", "")), []).append(
            {"id": identifier, **record})
    old_digests: dict[str, str] = snapshot.get("source_digests", {})

    tokenizer = get_tokenizer(settings.embed_model, settings.embed_cache_dir)
    all_chunks: list[Chunk] = []
    original_tokens = 0
    flag_changes = []
    for entry in entries:
        superseded = entry.status == "superseded"
        rows = rows_by_source.get(entry.source, [])
        if compatible and rows and old_digests.get(entry.source) == entry.sha256:
            pieces = _chunks_from_snapshot(rows, entry)
            if any(bool(r["metadata"].get("superseded")) != superseded for r in rows):
                flag_changes.append(entry.source)
            original_tokens += sum(piece.tokens for piece in pieces)
        else:
            raw = extracted.get(entry.source) or extract(entry.path, entry.doc_version,
                                                         superseded)
            raw.superseded = superseded
            raw.doc_version = entry.doc_version
            doc = clean(raw)
            original_tokens += sum(tokenizer.count(page.text) for page in doc.pages)
            pieces = chunk(doc, settings.chunk_size, settings.chunk_overlap, tokenizer,
                           settings.chunk_strategy)
            for piece in pieces:
                piece.superseded = superseded
        log("chunked", source=entry.source, status=entry.status, chunks=len(pieces))
        all_chunks.extend(pieces)
    if not all_chunks:
        raise ValueError("no indexable text remained after extraction and cleaning")
    digests = {entry.source: entry.sha256 for entry in entries}
    reusable, incremental = plan_incremental(all_chunks, digests, settings, snapshot)
    incremental["superseded_flag_changes"] = sorted(flag_changes)
    active = str(meta.get("index_version", ""))
    nothing_changed = (compatible and active and incremental["embedded_chunks"] == 0
                       and not (incremental["added"] or incremental["changed"]
                                or incremental["deleted"] or flag_changes))
    if nothing_changed:
        log("index unchanged: every document reused, active collection kept",
            collection=active, embedded_chunks=0, reused_chunks=incremental["reused_chunks"])
        incremental["published"] = False
        return {"collection": active, "chunks": len(all_chunks), "incremental": incremental}
    to_embed = [piece for piece in all_chunks if piece.id not in reusable]
    new_vectors = embed([piece.text for piece in to_embed], settings)
    vector_by_id = dict(reusable)
    vector_by_id.update({piece.id: vector for piece, vector in zip(to_embed, new_vectors)})
    vectors = [vector_by_id[piece.id] for piece in all_chunks]
    written = store(all_chunks, vectors, settings, client=client,
                    original_tokens=original_tokens, source_digests=digests,
                    incremental=incremental)
    incremental["published"] = True
    pointer = client.get_collection(name=f"{settings.collection}-active",
                                    embedding_function=None)
    collection = str((pointer.metadata or {}).get("active", ""))
    return {"collection": collection, "chunks": written, "incremental": incremental}


def _print_report_table(records: list[dict[str, Any]]) -> None:
    """A human-readable pass/fail table in the Job log (one line per document)."""
    print(f"{'document':48} {'quality':8} {'complete':8} {'recency':8} {'unique':8} disposition",
          flush=True)
    for record in records:
        checks = record["checks"]
        marks = ["PASS" if checks[name]["passed"] else "FAIL"
                 for name in ("quality", "completeness", "recency", "uniqueness")]
        print(f"{record['source'][:48]:48} {marks[0]:8} {marks[1]:8} {marks[2]:8} "
              f"{marks[3]:8} {record['disposition']}", flush=True)
        for name, check in checks.items():
            if not check["passed"]:
                print(f"    - {name}: {check['reason']}", flush=True)


def run_pipeline(settings: IndexerSettings, *, batch_dir: str | None = None,
                 batch_name: str | None = None, pre_actions: list[str] | None = None,
                 ) -> dict[str, Any]:
    run_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    lake = DataLake(settings.pipeline_data_dir)
    sources: dict[str, SourceDoc] = {}
    corpus_sources: set[str] | None = None
    if settings.corpus_dir and Path(settings.corpus_dir).is_dir():
        corpus = discover(settings.corpus_dir, "corpus")
        if not corpus:
            raise SystemExit(f"no documents found in {settings.corpus_dir}")
        corpus_sources = {doc.source for doc in corpus}
        sources.update({doc.source: doc for doc in corpus})
    batches: list[tuple[Path, str]] = []
    if batch_dir and Path(batch_dir).is_dir():
        # The Job mounts the optional ConfigMap `ingest-batch` here; empty means no batch.
        batches.append((Path(batch_dir), batch_name or Path(batch_dir).name))
    # Batches too large for a ConfigMap (about 750 KB of PDF) are copied to the PVC with
    # scripts/upload_batch.sh, one folder per batch: <pipeline-data>/incoming/<batch>/.
    incoming = Path(settings.pipeline_data_dir) / "incoming"
    if incoming.is_dir():
        batches += [(folder, folder.name) for folder in sorted(incoming.iterdir())
                    if folder.is_dir()]
    for folder, name in batches:
        batch = discover(str(folder), name)
        log("batch input", batch_dir=str(folder), batch_name=name, documents=len(batch))
        sources.update({doc.source: doc for doc in batch})
    if not sources and not lake.entries:
        raise SystemExit("no corpus, batch or data-lake documents to index")

    ingest = ingest_and_verify(settings, lake, run_id, list(sources.values()), corpus_sources)
    records = ingest["records"]
    _print_report_table(records) if records else log("no new or changed documents to verify")
    index = update_retrieval_sources(settings, lake, ingest["extracted"])
    incremental = index["incremental"]
    counts = {
        "documents_seen": len(sources),
        "unchanged": len(ingest["unchanged"]),
        "still_quarantined": len(ingest["still_quarantined"]),
        "verified": len(records),
        "passed": sum(r["passed"] for r in records),
        "quarantined": sum(r["disposition"] == "quarantine" for r in records),
        "archived_superseded_on_arrival": sum(r["disposition"] == "archive-superseded"
                                              for r in records),
        "lake_current": sum(e.status == "current" for e in lake.entries.values()),
        "lake_superseded": sum(e.status == "superseded" for e in lake.entries.values()),
        "lake_deleted": sum(e.status == "deleted" for e in lake.entries.values()),
        "embedded_chunks": incremental["embedded_chunks"],
        "reused_chunks": incremental["reused_chunks"],
    }
    report = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "inputs": {"corpus_dir": settings.corpus_dir, "batch_dir": batch_dir,
                   "batches": [str(folder) for folder, _name in batches]},
        "collection_prefix": settings.collection,
        "collection": index["collection"],
        "embed_model": settings.embed_model,
        "chunking": {"size": settings.chunk_size, "overlap": settings.chunk_overlap,
                     "strategy": settings.chunk_strategy},
        "summary": counts,
        "documents": records,
        "unchanged_documents": ingest["unchanged"],
        "still_quarantined_documents": ingest["still_quarantined"],
        "lake_actions": [*(pre_actions or []), *ingest["lake_actions"]],
        "incremental": incremental,
    }
    report_dir = Path(os.environ.get(
        "VERIFICATION_REPORT_DIR",
        str(Path(settings.pipeline_data_dir) / "eval" / "results" / "verification")))
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{run_id}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for action in report["lake_actions"]:
        log("lake", action=action)
    log("verification report written", report=str(report_path), **counts)
    return {"run_id": run_id, "verification_report": str(report_path),
            "collection": index["collection"], "summary": counts}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest, verify and index, then exit.")
    parser.add_argument("--dummy", action="store_true", help="write three fake chunks")
    parser.add_argument("--restore", action="store_true",
                        help="point the active alias at the previous complete collection")
    parser.add_argument("--batch-dir", default=os.environ.get("BATCH_DIR") or None,
                        help="extra directory of documents to ingest (env BATCH_DIR)")
    parser.add_argument("--batch-name", default=os.environ.get("BATCH_NAME") or None)
    parser.add_argument("--restore-version", metavar="SOURCE",
                        help="make an archived (superseded or deleted) version current again")
    parser.add_argument("--version", help="with --restore-version: the expected version")
    parser.add_argument("--delete", metavar="SOURCE",
                        help="archive a document as deleted and remove its chunks")
    args = parser.parse_args()
    settings = get_settings()
    log("indexer starting", dummy=args.dummy, embed_model=settings.embed_model,
        collection=settings.collection, chroma=f"{settings.chroma_host}:{settings.chroma_port}",
        chunk_size=settings.chunk_size, batch_dir=args.batch_dir,
        pod=os.environ.get("HOSTNAME", "-"))
    started = time.perf_counter()
    try:
        if args.restore:
            from .store import restore_previous

            log("previous index restored", collection=restore_previous(settings))
            return 0
        if args.dummy:
            from .dummy import write_dummy_index
            from .store import get_client

            count = write_dummy_index(settings, get_client(settings))
            log("indexer finished", chunks=count, seconds=round(time.perf_counter() - started, 1))
            return 0
        pre_actions = []
        if args.restore_version or args.delete:
            lake = DataLake(settings.pipeline_data_dir)
            if args.restore_version:
                pre_actions.append(lake.restore(args.restore_version, args.version))
            if args.delete:
                pre_actions.append(lake.delete(args.delete, "deleted by operator"))
            lake.save()
        summary = run_pipeline(settings, batch_dir=args.batch_dir, batch_name=args.batch_name,
                               pre_actions=pre_actions)
        log("indexer finished", **summary, seconds=round(time.perf_counter() - started, 1))
        return 0
    except NotImplementedError as exc:
        log("indexer stage not implemented yet", error=str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
