#!/usr/bin/env python3
"""Score a running RAHBAR against a golden set, and gate CI on the result (section 5).

    python eval/run_eval.py --api http://<ingress>                 # your corpus
    python eval/run_eval.py --api ... --golden eval/fixtures/golden.fixture.yaml
    python eval/run_eval.py --api ... --update-baseline            # after a deliberate improvement

Exit code 0 when every gate passes, 1 when any fails. CI relies on that exit code.

Results and baseline use the flat shape in docs/architecture/data-models.md
(§ Evaluation files); the matching rules are in the same file (§ Matching rules).
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


# The canned fallback answer starts like this (validation-and-errors.md § Retry and fallback).
FALLBACK_MARKER = "reliable, cited answer"


def _is_fallback(response: dict) -> bool:
    return FALLBACK_MARKER in str(response.get("answer", "")) and not response.get("citations")


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def summarise(rows: list[dict]) -> dict:
    """Overall recall@3, recall@5, citation validity and abstention correctness, plus
    recall by question type. This dict becomes results.json (data-models.md § Evaluation
    files): the gate reads the top-level keys, and `rows` keeps one slim line per question."""
    slim = []
    citations_total = citations_valid = 0.0
    for row in rows:
        response = row.get("response") or {}
        retrieved = response.get("retrieved") or []
        relevant = row.get("relevant") or []
        validity = citation_validity(response)
        n_citations = len(response.get("citations") or [])
        if validity is not None:
            citations_total += n_citations
            citations_valid += validity * n_citations
        slim.append({
            "id": row.get("id"),
            "type": row.get("type", "ordinary"),
            "must_abstain": bool(row.get("must_abstain", False)),
            "recall@3": recall_at_k(relevant, retrieved, 3),
            "recall@5": recall_at_k(relevant, retrieved, 5),
            "top_score": max((float(r.get("score", 0.0)) for r in retrieved), default=None),
            "citation_validity": validity,
            "answered_from_context": bool(response.get("answered_from_context", False)),
            "cached": bool(response.get("cached", False)),
            "fallback": _is_fallback(response),
            "seconds": row.get("seconds"),
        })
    abstain = [not r["answered_from_context"] for r in slim if r["must_abstain"]]
    by_type = {}
    for kind in sorted({r["type"] for r in slim}):
        subset = [r for r in slim if r["type"] == kind]
        by_type[kind] = {"n": len(subset),
                         "recall@3": _mean([r["recall@3"] for r in subset]),
                         "recall@5": _mean([r["recall@5"] for r in subset])}
    return {
        "recall@3": _mean([r["recall@3"] for r in slim]),
        "recall@5": _mean([r["recall@5"] for r in slim]),
        "citation_validity": citations_valid / citations_total if citations_total else None,
        "abstention_correctness": sum(abstain) / len(abstain) if abstain else None,
        "by_type": by_type,
        "cache_hits": sum(r["cached"] for r in slim),
        "fallbacks": sum(r["fallback"] for r in slim),
        "rows": slim,
    }


def gate(results: dict, baseline: dict | None, *, allow_missing_baseline: bool = False) -> list[str]:
    """Return one message per failed gate (section 5.4); an empty list means pass.

    Fails when: recall@5 is more than MAX_RECALL5_DROP below the baseline; abstention
    correctness is below REQUIRED_ABSTENTION or the golden set has no must-abstain question;
    citation validity is below MIN_CITATION_VALIDITY; or the baseline is missing (unless
    allow_missing_baseline, used with --update-baseline). No citations at all is a warning."""
    failures = []
    if baseline is None:
        if not allow_missing_baseline:
            failures.append("baseline file is missing (run once with --update-baseline)")
    else:
        recall, base = results.get("recall@5"), baseline.get("recall@5")
        if recall is None or base is None:
            failures.append("recall@5 could not be compared with the baseline")
        elif recall < base - MAX_RECALL5_DROP - 1e-9:
            failures.append(f"recall@5 {recall:.3f} is more than {MAX_RECALL5_DROP:.0%} "
                            f"below the baseline {base:.3f}")
    abstention = results.get("abstention_correctness")
    if abstention is None:
        failures.append("the golden set has no must-abstain question")
    elif abstention < REQUIRED_ABSTENTION:
        failures.append(f"abstention correctness {abstention:.0%} is below "
                        f"{REQUIRED_ABSTENTION:.0%}: a must-abstain question was answered")
    validity = results.get("citation_validity")
    if validity is None:
        print("warning: no answer carried a citation, so citation validity was not measured")
    elif validity < MIN_CITATION_VALIDITY:
        failures.append(f"citation validity {validity:.1%} is below {MIN_CITATION_VALIDITY:.0%}")
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
    parser.add_argument("--pause", type=float, default=0.0, metavar="SECONDS",
                        help="wait between questions (useful when measuring uncached retrieval)")
    args = parser.parse_args()
    if args.pause < 0:
        parser.error("--pause must be non-negative")

    questions = load_golden(args.golden)
    rows = []
    headers = {"Host": args.host} if args.host else {}
    with httpx.Client(timeout=120.0, headers=headers) as client:
        for index, q in enumerate(questions):
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
            if args.pause and index < len(questions) - 1:
                time.sleep(args.pause)

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
