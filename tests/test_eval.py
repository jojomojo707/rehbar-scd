from eval.run_eval import citation_validity, gate, recall_at_k, summarise


def test_recall_at_k_prefix_match() -> None:
    gold = [{"source": "Rules.pdf", "section": "5.4"}]
    assert recall_at_k(gold, [{"source": "rules.pdf", "section": "5.4 Academic Warning"}], 3) == 1
    assert recall_at_k(gold, [{"source": "Rules.pdf", "section": "5.41"}], 3) == 0


def test_citation_validity_uses_own_retrieved_and_page() -> None:
    response = {"citations": [{"source": "a.pdf", "section": "1", "page": 2},
                              {"source": "b.pdf", "section": "2"}],
                "retrieved": [{"source": "a.pdf", "section": "1", "page": 3}]}
    assert citation_validity(response) == 0
    assert citation_validity({"citations": [], "retrieved": []}) is None


def _row(kind, relevant, retrieved, citations=(), answered=True, **extra):
    response = {"retrieved": retrieved, "citations": list(citations),
                "answered_from_context": answered, "answer": "ok", **extra}
    return {"id": kind, "type": kind, "must_abstain": kind == "abstain",
            "relevant": relevant, "response": response, "seconds": 1.0}


def test_summarise_by_type_uses_the_flat_shape_from_data_models() -> None:
    hit = {"source": "a.pdf", "section": "1 Intro", "page": 1, "score": 0.8}
    rows = [
        _row("ordinary", [{"source": "a.pdf", "section": "1"}], [hit],
             citations=[{"source": "a.pdf", "section": "1 Intro", "page": 1}]),
        _row("exact", [{"source": "a.pdf", "section": "9"}], [hit]),
        _row("abstain", [], [], answered=False),
    ]
    result = summarise(rows)
    # Top-level keys, not nested under "overall" (data-models.md § Evaluation files).
    assert result["recall@5"] == 0.5 and result["recall@3"] == 0.5
    assert result["citation_validity"] == 1.0
    assert result["abstention_correctness"] == 1.0
    assert result["by_type"]["ordinary"] == {"n": 1, "recall@3": 1.0, "recall@5": 1.0}
    assert result["by_type"]["exact"]["recall@5"] == 0.0
    assert result["by_type"]["abstain"]["recall@5"] is None
    assert result["cache_hits"] == 0 and result["fallbacks"] == 0
    assert result["rows"][0]["top_score"] == 0.8
    assert "response" not in result["rows"][0]      # slim rows only


def test_summarise_counts_cache_hits_and_fallbacks() -> None:
    fallback = "I couldn't produce a reliable, cited answer right now. Please try again."
    rows = [_row("ordinary", [], [], cached=True),
            _row("ordinary", [], [], answered=False, answer=fallback)]
    rows[1]["response"]["answer"] = fallback
    result = summarise(rows)
    assert result["cache_hits"] == 1 and result["fallbacks"] == 1


def test_gate_conditions() -> None:
    baseline = {"recall@5": 0.9}
    good = {"recall@5": 0.86, "citation_validity": 1.0, "abstention_correctness": 1.0}
    assert gate(good, baseline) == []                       # 4 points down is allowed
    assert gate({**good, "recall@5": 0.84}, baseline)       # 6 points down fails
    assert gate({**good, "abstention_correctness": 0.5}, baseline)
    assert gate({**good, "abstention_correctness": None}, baseline)   # no must-abstain question
    assert gate({**good, "citation_validity": 0.9}, baseline)
    assert gate({**good, "citation_validity": None}, baseline) == []  # warning only
    assert gate(good, None)                                 # baseline missing
    assert gate(good, None, allow_missing_baseline=True) == []
