#!/usr/bin/env python3
"""Validate the Assignment 03 golden set and embedding-pair dataset."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path.name}:{number}: each JSONL row must be an object")
        rows.append(row)
    return rows


def validate_golden() -> int:
    rows = read_jsonl(ROOT / "golden.jsonl")
    ids = [row.get("id") for row in rows]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        raise ValueError("golden case IDs must be present and unique")

    counts = {key: sum(row.get("bucket") == key for row in rows)
              for key in ("answerable", "unanswerable", "hard")}
    if len(rows) < 25 or counts["answerable"] < 15 or counts["unanswerable"] < 5 or counts["hard"] < 5:
        raise ValueError(f"golden set below minimum counts: {counts}")

    for row in rows:
        if row.get("origin") not in {"human", "synthetic"}:
            raise ValueError(f"{row['id']}: origin must be human or synthetic")
        if row.get("answerable"):
            if not row.get("gold_answer") or not row.get("gold"):
                raise ValueError(f"{row['id']}: answerable row requires answer and gold locations")
            for location in row["gold"]:
                if not location.get("document") or not isinstance(location.get("page"), int):
                    raise ValueError(f"{row['id']}: each gold location needs document and integer page")
                if location["page"] < 1:
                    raise ValueError(f"{row['id']}: gold page numbers are 1-based")
        elif row.get("bucket") == "unanswerable":
            if not row.get("must_abstain") or row.get("gold"):
                raise ValueError(f"{row['id']}: unanswerable case must abstain and have no gold location")

    carried = sum("carried forward from eval/golden.yaml" in row.get("authored_by", "")
                  for row in rows)
    reviewed_synthetic = sum(
        row.get("origin") == "synthetic"
        and row.get("manual_review", {}).get("status") in {"reviewed", "verified"}
        for row in rows
    )
    if carried < 8:
        raise ValueError(f"only {carried} cases carried forward from team golden set; need at least 8")
    if reviewed_synthetic < 8:
        raise ValueError(f"only {reviewed_synthetic} synthetic cases manually reviewed; need at least 8")
    print(f"golden: {len(rows)} cases ({counts}); {carried} carried team cases; "
          f"{reviewed_synthetic} synthetic cases manually checked")
    return len(rows)


def validate_pairs() -> int:
    data = json.loads((ROOT / "module_pairs.json").read_text(encoding="utf-8"))
    positives, negatives = data.get("paraphrase_pairs", []), data.get("unrelated_pairs", [])
    if len(positives) < 15 or len(negatives) < 15:
        raise ValueError("module evaluation requires at least 15 pairs of each type")
    for group in (positives, negatives):
        ids = [row.get("id") for row in group]
        if len(ids) != len(set(ids)):
            raise ValueError("pair IDs must be unique within each pair type")
        if any(not row.get("a", "").strip() or not row.get("b", "").strip() for row in group):
            raise ValueError("each pair needs two non-empty texts")
    print(f"module pairs: {len(positives)} paraphrase and {len(negatives)} unrelated")
    return len(positives) + len(negatives)


def main() -> int:
    validate_golden()
    validate_pairs()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
