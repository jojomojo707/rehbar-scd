"""The indexer Job's entry point. It runs once and exits (section 4.2).

    python -m pipeline.run --dummy    # week 1: three fake chunks, no model needed
    python -m pipeline.run            # the real pipeline: extract, clean, chunk, embed, store

Exit code 0 means the index was written; anything else fails the Job, and
Kubernetes retries it up to the Job's backoffLimit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import IndexerSettings, get_settings
from .models import Chunk
from .tokens import get_tokenizer


def log(msg: str, **fields: object) -> None:
    print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                      "logger": "rahbar.indexer", "msg": msg, **fields}), flush=True)


def _front_matter(path: Path) -> dict[str, str]:
    """Read `key: value` lines between leading '---' markers (used by eval/fixtures)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta


def discover(corpus_dir: str) -> list[tuple[Path, str, bool]]:
    """List (path, doc_version, superseded) for every document to index.

    corpus/fetch.py writes _index.json next to the files it downloads; use it when
    present. Otherwise read Markdown front matter (the CI fixtures work this way).
    """
    root = Path(corpus_dir)
    index = root / "_index.json"
    if index.exists():
        entries = json.loads(index.read_text(encoding="utf-8"))
        return [(root / e["file"], str(e.get("doc_version", "unknown")),
                 bool(e.get("superseded", False))) for e in entries]
    found = []
    for path in sorted(root.glob("*")):
        if path.suffix.lower() not in {".pdf", ".md", ".html", ".txt"}:
            continue
        if path.name.lower().startswith("readme"):
            continue
        meta = _front_matter(path) if path.suffix.lower() == ".md" else {}
        found.append((path, meta.get("doc_version", "unknown"),
                      meta.get("superseded", "false").lower() == "true"))
    return found


def _persist_verification_artifacts(
    records: list[dict[str, object]], *, run_id: str,
    quarantine_dir: str, report_dir: str,
) -> Path:
    """Copy rejected source files and write a report for this ingestion run."""
    quarantine_root = Path(quarantine_dir) / run_id
    for index, record in enumerate(records, start=1):
        if record["passed"]:
            continue
        source_path = Path(str(record["path"]))
        destination = quarantine_root / f"{index:04d}-{source_path.name}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        record["quarantined_to"] = str(destination)

    report_path = Path(report_dir) / f"{run_id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    failed = sum(not bool(record["passed"]) for record in records)
    report = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"documents": len(records), "passed": len(records) - failed,
                    "failed": failed},
        "documents": records,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    return report_path


def run_pipeline(settings: IndexerSettings) -> dict[str, object]:
    from .chunk import chunk
    from .clean import clean
    from .embed import embed
    from .extract import extract
    from .store import active_snapshot, get_client, plan_incremental, store
    from .verify import verify_documents

    documents = discover(settings.corpus_dir)
    if not documents:
        raise SystemExit(f"no documents found in {settings.corpus_dir}")
    run_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    records: list[dict[str, object]] = []
    extracted = []
    extracted_paths: list[Path] = []
    for path, version, superseded in documents:
        try:
            extracted.append(extract(str(path), version, superseded))
            extracted_paths.append(path)
        except Exception as exc:
            records.append({
                "source": path.name, "path": str(path), "doc_version": version,
                "passed": False,
                "checks": {"extraction": {"passed": False,
                                             "reason": f"{type(exc).__name__}: {exc}"}},
            })
    verification = verify_documents(
        extracted, embed=lambda texts: embed(texts, settings))
    for path, document, result in zip(extracted_paths, extracted, verification):
        records.append({
            "source": result.source, "path": str(path), "doc_version": document.doc_version,
            "passed": result.passed,
            "checks": {name: {"passed": check.passed, "reason": check.reason}
                       for name, check in result.checks.items()},
        })
    data_root = Path(settings.pipeline_data_dir)
    report_path = _persist_verification_artifacts(
        records, run_id=run_id,
        quarantine_dir=os.environ.get("QUARANTINE_DIR", str(data_root / "quarantine")),
        report_dir=os.environ.get(
            "VERIFICATION_REPORT_DIR", str(data_root / "eval" / "results" / "verification")
        ),
    )
    log("verification report written", run_id=run_id, report=str(report_path),
        passed=sum(bool(record["passed"]) for record in records),
        failed=sum(not bool(record["passed"]) for record in records))
    failed = [item for item in verification if not item.passed]
    failed_records = [record for record in records if not record["passed"]]
    if failed or failed_records:
        reasons = {str(record["source"]): record["checks"] for record in failed_records}
        raise ValueError(f"document verification failed; report={report_path}: "
                         f"{json.dumps(reasons, sort_keys=True)}")
    all_chunks: list[Chunk] = []
    tokenizer = get_tokenizer(settings.embed_model, settings.embed_cache_dir)
    original_tokens = 0
    skipped = 0
    for path, raw_doc in zip((item[0] for item in documents), extracted):
        doc = clean(raw_doc)
        original_tokens += sum(tokenizer.count(page.text) for page in doc.pages)
        pieces = chunk(doc, settings.chunk_size, settings.chunk_overlap, tokenizer, settings.chunk_strategy)
        log("chunked", source=path.name, chunks=len(pieces))
        skipped += int(not pieces)
        all_chunks.extend(pieces)
    if not all_chunks:
        raise ValueError("no indexable text remained after extraction and cleaning")
    source_digests = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path, _version, _superseded in documents
    }
    client = get_client(settings)
    snapshot = active_snapshot(settings, client)
    reusable, incremental = plan_incremental(all_chunks, source_digests, settings, snapshot)
    chunks_to_embed = [chunk for chunk in all_chunks if chunk.id not in reusable]
    new_vectors = embed([chunk.text for chunk in chunks_to_embed], settings)
    vector_by_id = dict(reusable)
    vector_by_id.update({chunk.id: vector for chunk, vector in zip(chunks_to_embed, new_vectors)})
    vectors = [vector_by_id[chunk.id] for chunk in all_chunks]
    stored = store(all_chunks, vectors, settings, client=client,
                   original_tokens=original_tokens, source_digests=source_digests,
                   incremental=incremental)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["incremental"] = incremental
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    stored_tokens = sum(item.tokens for item in all_chunks)
    pointer = f"{settings.collection}-active"
    collection = settings.collection
    try:
        from .store import get_client

        metadata = get_client(settings).get_collection(name=pointer, embedding_function=None).metadata or {}
        collection = str(metadata.get("active", collection))
    except Exception:
        pass
    return {
        "collection": collection,
        "verification_report": str(report_path),
        "incremental": incremental,
        "chunks": stored,
        "documents": len(documents),
        "skipped": skipped,
        "original_tokens": original_tokens,
        "stored_tokens": stored_tokens,
        "amplification": round(stored_tokens / original_tokens, 3) if original_tokens else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the RAHBAR index, then exit.")
    parser.add_argument("--dummy", action="store_true", help="write three fake chunks")
    parser.add_argument("--restore", action="store_true",
                        help="restore the previous complete index and exit")
    args = parser.parse_args()
    settings = get_settings()
    log("indexer starting", dummy=args.dummy, embed_model=settings.embed_model,
        collection=settings.collection, chroma=f"{settings.chroma_host}:{settings.chroma_port}",
        pod=os.environ.get("HOSTNAME", "-"))
    started = time.perf_counter()
    try:
        if args.restore:
            from .store import restore_previous

            restored = restore_previous(settings)
            log("previous index restored", collection=restored)
            return 0
        if args.dummy:
            from .dummy import write_dummy_index
            from .store import get_client

            count = write_dummy_index(settings, get_client(settings))
        else:
            summary = run_pipeline(settings)
            log("indexer finished", **summary, seconds=round(time.perf_counter() - started, 1))
            return 0
    except NotImplementedError as exc:
        log("indexer stage not implemented yet", error=str(exc))
        return 2
    log("indexer finished", chunks=count, seconds=round(time.perf_counter() - started, 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
