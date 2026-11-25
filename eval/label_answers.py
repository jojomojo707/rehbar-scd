#!/usr/bin/env python3
"""Hand-label answers for faithfulness, then measure how often the LLM judge agrees (Part B).

    python eval/label_answers.py --run eval/results/<stamp>-baseline --count 10   # label
    python eval/label_answers.py --run eval/results/<stamp>-baseline --report     # agreement

Labelling shows one answered question at a time: the question, the context passages the model
saw (from its trace) and the answer. Type y if every claim in the answer is supported by the
context, n if any claim is not, s to skip. The judge's verdict is hidden while you label.
Labels are saved to eval/human_labels.json (keyed by question id + answer hash), so later suite
runs that produce the same answer also report agreement.
"""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_rows(run: Path) -> list[dict]:
    data = json.loads((run / "e2e-run-1.json").read_text(encoding="utf-8"))
    return [r for r in data["rows"] if r.get("faithfulness", {}).get("faithful") is not None]


def answer_sha(row: dict) -> str:
    import hashlib
    return hashlib.sha256(f"{row['id']}\n{row['answer']}".encode()).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", type=Path, required=True, help="a run_suite result folder")
    parser.add_argument("--labels", type=Path, default=HERE / "human_labels.json")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--labeller", default="")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    rows = load_rows(args.run)
    store = json.loads(args.labels.read_text()) if args.labels.is_file() else {"labels": []}
    by_sha = {label["answer_sha"]: label for label in store["labels"]}

    if not args.report:
        labeller = args.labeller or input("Your name (recorded with each label): ").strip()
        done = 0
        for row in rows:
            if done >= args.count:
                break
            sha = answer_sha(row)
            if sha in by_sha:
                continue
            print("\n" + "=" * 100)
            print(f"[{row['id']}] QUESTION: {row['question']}\n\nCONTEXT:")
            for i, passage in enumerate(row.get("context") or [], 1):
                print(f"  [{i}] {passage.get('document')} / {passage.get('section')} "
                      f"(page {passage.get('page')})")
                print(textwrap.indent(textwrap.fill(str(passage.get("text") or ""), 96), "      "))
            print(f"\nANSWER: {row['answer']}")
            choice = ""
            while choice not in {"y", "n", "s"}:
                choice = input("\nIs every claim supported by the context? [y/n/s] ").strip().lower()
            if choice == "s":
                continue
            by_sha[sha] = {"id": row["id"], "answer_sha": sha, "faithful": choice == "y",
                           "labeller": labeller, "run": args.run.name}
            done += 1
            store["labels"] = list(by_sha.values())
            args.labels.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")
        print(f"\n{done} new labels saved to {args.labels}")

    pairs = [(by_sha[answer_sha(r)]["faithful"], r["faithfulness"]["faithful"], r["id"])
             for r in rows if answer_sha(r) in by_sha]
    agree = sum(human == judge for human, judge, _ in pairs)
    print(f"\nhand-labelled answers in this run: {len(pairs)}")
    if pairs:
        print(f"judge agrees with the human label on {agree}/{len(pairs)} = "
              f"{agree / len(pairs):.1%}")
        for human, judge, qid in pairs:
            if human != judge:
                print(f"  disagreement {qid}: human={'faithful' if human else 'unfaithful'} "
                      f"judge={'faithful' if judge else 'unfaithful'}")
        print(f"human-labelled faithfulness: {sum(h for h, _, _ in pairs)}/{len(pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
