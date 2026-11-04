#!/usr/bin/env python3
"""Score a running RAHBAR against a golden set, and gate CI on the result (section 5).

    python eval/run_eval.py --api http://<ingress>                 # your corpus
    python eval/run_eval.py --api ... --golden eval/fixtures/golden.fixture.yaml
    python eval/run_eval.py --api ... --update-baseline            # after a deliberate improvement

Exit code 0 when every gate passes, 1 when any fails. CI relies on that exit code.

Given: talking to the API, reading the golden set, writing results.json, the exit
code. Yours: the four functions marked STARTER-TODO. They are the evaluation.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent

# The gate from section 5.4. Change these only with a reason written in docs/PIPELINE.md.
MAX_RECALL5_DROP = 0.05        # recall@5 may fall at most 5 points below the baseline
MIN_CITATION_VALIDITY = 0.95   # at least 95% of citations must match retrieved passages
REQUIRED_ABSTENTION = 1.0      # every must-abstain question must be declined


def load_golden(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = data.get("questions") or []
    if not questions:
        sys.exit(f"no questions in {path}")
    return questions


def ask(client: httpx.Client, api: str, question: str) -> dict:
    """POST one question and return the AskResponse as a dict (see api/app/schemas.py)."""
    response = client.post(f"{api.rstrip('/')}/api/ask", json={"question": question})
    response.raise_for_status()
    return response.json()


def recall_at_k(relevant: list[dict], retrieved: list[dict], k: int) -> float | None:
    """Fraction of the relevant (source, section) pairs found in the top k retrieved.
    Return None when the question has no relevant passages (must-abstain questions)."""
    if not relevant:
        return None
    def norm(value: object) -> str:
        return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split()).rstrip(" .:")
    found = set()
    for item in retrieved[:k]:
        source, section = norm(item.get("source", "")), norm(item.get("section", ""))
        for gold in relevant:
            gs, sec = norm(gold.get("source", "")), norm(gold.get("section", ""))
            if source == gs and (section == sec or section.startswith(sec + " ") or section.startswith(sec + ".") or section.startswith(sec + ")")):
                found.add((gs, sec))
    expected = {(norm(x.get("source", "")), norm(x.get("section", ""))) for x in relevant}
    return len(found & expected) / len(expected) if expected else None


def citation_validity(response: dict) -> float | None:
    """Fraction of the response's citations that match a passage in response['retrieved'].
    Return None when there are no citations."""
    citations = response.get("citations") or []
    if not citations:
        return None
    retrieved = response.get("retrieved") or []
    def norm(value: object) -> str:
        return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split()).rstrip(" .:")
    valid = 0
    for citation in citations:
        for passage in retrieved:
            if norm(citation.get("source")) != norm(passage.get("source")) or norm(citation.get("section")) != norm(passage.get("section")):
                continue
            cp, pp = citation.get("page"), passage.get("page")
            if cp is None or cp == pp:
                valid += 1
                break
    return valid / len(citations)


def summarise(rows: list[dict]) -> dict:
    """Overall recall@3, recall@5, citation validity and abstention correctness, plus
    recall@5 broken down by question type. This dict becomes results.json."""
    def mean(key: str, selected: list[dict]) -> float | None:
        values = [r[key] for r in selected if r.get(key) is not None]
        return sum(values) / len(values) if values else None
    for row in rows:
        response = row.get("response") or {}
        row["recall@3"] = recall_at_k(row.get("relevant") or [], response.get("retrieved") or [], 3)
        row["recall@5"] = recall_at_k(row.get("relevant") or [], response.get("retrieved") or [], 5)
        row["citation_validity"] = citation_validity(response)
        row["abstention_correct"] = (not bool(response.get("answered_from_context", True))) if row.get("must_abstain") else None
    r3, r5 = mean("recall@3", rows), mean("recall@5", rows)
    citation_total = sum(len((r.get("response") or {}).get("citations") or []) for r in rows)
    valid_total = round(sum((r["citation_validity"] or 0) * len((r.get("response") or {}).get("citations") or []) for r in rows))
    abstain = [r["abstention_correct"] for r in rows if r["abstention_correct"] is not None]
    by_type = {}
    for kind in sorted({r.get("type", "ordinary") for r in rows}):
        subset = [r for r in rows if r.get("type", "ordinary") == kind]
        by_type[kind] = {"questions": len(subset), "recall@3": mean("recall@3", subset), "recall@5": mean("recall@5", subset)}
    return {"overall": {"questions": len(rows), "recall@3": r3, "recall@5": r5,
                         "citation_validity": valid_total / citation_total if citation_total else None,
                         "citation_count": citation_total, "valid_citation_count": valid_total,
                         "abstention_correctness": sum(abstain) / len(abstain) if abstain else None,
                         "must_abstain_count": len(abstain)}, "by_type": by_type, "rows": rows}


def gate(results: dict, baseline: dict | None, *, allow_missing_baseline: bool = False) -> list[str]:
    """Return one message per failed gate (section 5.4); an empty list means pass."""
    failures = []
    overall = results.get("overall", results)
    recall = overall.get("recall@5")
    if baseline is None and not allow_missing_baseline:
        failures.append("baseline is missing")
    elif baseline is not None:
        base = baseline.get("overall", baseline).get("recall@5")
        if recall is None or base is None or recall < base - MAX_RECALL5_DROP - 1e-12:
            failures.append(f"recall@5 dropped more than {MAX_RECALL5_DROP:.0%} below baseline")
    abstain = overall.get("abstention_correctness")
    if overall.get("must_abstain_count", 0) and (abstain is None or abstain < REQUIRED_ABSTENTION):
        failures.append("must-abstain questions were answered from context")
    validity = overall.get("citation_validity")
    if validity is not None and validity < MIN_CITATION_VALIDITY:
        failures.append(f"citation validity below {MIN_CITATION_VALIDITY:.0%}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAHBAR against a golden set.")
    parser.add_argument("--api", required=True, help="base URL, e.g. http://192.168.49.2")
    parser.add_argument("--host", help="Host header, when your Ingress rule names a host")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.yaml")
    parser.add_argument("--baseline", type=Path, default=HERE / "baseline.json")
    parser.add_argument("--out", type=Path, default=HERE / "results.json")
    parser.add_argument("--update-baseline", action="store_true",
                        help="write these results as the new baseline")
    args = parser.parse_args()

    questions = load_golden(args.golden)
    rows = []
    headers = {"Host": args.host} if args.host else {}
    with httpx.Client(timeout=120.0, headers=headers) as client:
        for q in questions:
            started = time.perf_counter()
            response = ask(client, args.api, q["question"])
            rows.append({
                "id": q["id"], "type": q.get("type", "ordinary"),
                "must_abstain": bool(q.get("must_abstain", False)),
                "relevant": q.get("relevant") or [],
                "expect": q.get("expect"),
                "response": response,
                "seconds": round(time.perf_counter() - started, 2),
            })
            print(f"  {q['id']:<5} {rows[-1]['seconds']:>6.2f}s  {q['question'][:60]}")

    try:
        results = summarise(rows)
        baseline = json.loads(args.baseline.read_text()) if args.baseline.exists() else None
        failures = gate(results, baseline, allow_missing_baseline=args.update_baseline)
    except NotImplementedError as exc:
        print(f"\nnot implemented yet: {exc}")
        return 2

    results["golden"] = str(args.golden)
    results["questions"] = len(rows)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nresults written to {args.out}")
    if args.update_baseline and not failures:
        args.baseline.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"baseline updated: {args.baseline}")

    if failures:
        print("\nGATE FAILED")
        for message in failures:
            print(f"  - {message}")
        return 1
    print("\ngate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
