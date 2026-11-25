"""Count chunks per document id directly in Chroma (orphan check for deletions).

    python -m pipeline.counts                    # active collection of CHROMA_COLLECTION
    python -m pipeline.counts --source fees.md   # also query one document id explicitly
    python -m pipeline.counts --previous         # the collection before the active one

Prints one line per document with its chunk count and superseded flag. When --source names a
deleted document, the count it prints must be 0.
"""

from __future__ import annotations

import argparse
import json

from .config import get_settings
from .store import get_client


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", default=[],
                        help="document id (source file name) to count explicitly")
    parser.add_argument("--previous", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    client = get_client(settings)
    pointer = client.get_collection(name=f"{settings.collection}-active",
                                    embedding_function=None)
    meta = pointer.metadata or {}
    name = str(meta.get("previous" if args.previous else "active", ""))
    collection = client.get_collection(name=name, embedding_function=None)
    rows = collection.get(include=["metadatas"])
    counts: dict[str, dict[str, object]] = {}
    for row in rows.get("metadatas") or []:
        source = str(row.get("source", ""))
        item = counts.setdefault(source, {"chunks": 0, "superseded": bool(row.get("superseded")),
                                          "doc_version": row.get("doc_version")})
        item["chunks"] = int(item["chunks"]) + 1  # type: ignore[call-overload]
    print(f"collection {name}: {collection.count()} chunks, {len(counts)} documents")
    print(f"{'document id':52} {'version':10} {'superseded':10} chunks")
    for source, item in sorted(counts.items()):
        print(f"{source:52} {str(item['doc_version']):10} {str(item['superseded']):10} "
              f"{item['chunks']}")
    for source in args.source:
        found = collection.get(where={"source": source}, include=[])
        print(f"where source == {source!r}: {len(found.get('ids') or [])} chunks")
    print(json.dumps({"collection": name, "documents": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
