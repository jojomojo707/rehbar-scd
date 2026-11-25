#!/usr/bin/env python3
"""Hand-review synthetic golden questions (Part B: at least 8 reviewed by a team member).

    python eval/review_synthetic.py

For each synthetic question still pending, it shows the question, the expected answer and the
gold location. Open the source (corpus/raw/<document> or eval/batches/batch-b/<document>) and
check them, then type a to accept, f to flag a problem (you are asked for a note), s to skip,
q to stop. An AI pre-check note (status ai-checked / ai-flagged) is shown when there is one;
it is a hint only and does not count as a hand review. Accepted questions get manual_review.status=reviewed and your name.
"""

from __future__ import annotations

import json
from pathlib import Path

GOLDEN = Path(__file__).resolve().parent / "golden.jsonl"


def main() -> int:
    rows = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    name = input("Your name (recorded as reviewer): ").strip()
    if not name:
        print("a reviewer name is required")
        return 2
    for row in rows:
        review = row.get("manual_review") or {}
        if row.get("origin") != "synthetic" or review.get("status") == "reviewed":
            continue
        print("\n" + "=" * 90)
        print(f"[{row['id']}] ({row['bucket']}) {row['question']}")
        print(f"expected answer: {row.get('gold_answer') or '(must abstain: no answer in corpus)'}")
        for gold in row.get("gold") or []:
            print(f"gold location:   {gold['document']}  page {gold.get('page')}  "
                  f"section {gold.get('section')}")
        if review.get("status", "").startswith("ai-"):
            print(f"AI pre-check ({review['status']}): {review.get('note')}")
        choice = ""
        while choice not in {"a", "f", "s", "q"}:
            choice = input("[a]ccept / [f]lag / [s]kip / [q]uit: ").strip().lower()
        if choice == "q":
            break
        if choice == "a":
            row["manual_review"] = {"status": "reviewed", "reviewer": name,
                                    "note": input("note (optional): ").strip() or
                                    "Question, answer and location checked against the source.",
                                    "ai_precheck": review.get("note", "")
                                    if review.get("status", "").startswith("ai-") else ""}
        elif choice == "f":
            row["manual_review"] = {"status": "flagged", "reviewer": name,
                                    "note": input("what is wrong: ").strip()}
        GOLDEN.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                          encoding="utf-8")
    reviewed = sum(r.get("origin") == "synthetic" and
                   (r.get("manual_review") or {}).get("status") == "reviewed" for r in rows)
    print(f"\n{reviewed} synthetic questions reviewed (the brief needs at least 8)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
