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


def test_summarise_includes_types_citations_and_abstentions() -> None:
    rows = [{"type": "ordinary", "relevant": [{"source": "a", "section": "1"}],
             "response": {"retrieved": [{"source": "a", "section": "1"}],
                          "citations": [{"source": "a", "section": "1"}], "answered_from_context": True}},
            {"type": "abstain", "must_abstain": True, "relevant": [],
             "response": {"retrieved": [], "citations": [], "answered_from_context": False}}]
    result = summarise(rows)
    assert result["overall"]["recall@5"] == 1
    assert result["overall"]["citation_validity"] == 1
    assert result["overall"]["abstention_correctness"] == 1
    assert result["by_type"]["abstain"]["recall@5"] is None


def test_gate_conditions() -> None:
    baseline = {"overall": {"recall@5": 0.9}}
    results = {"overall": {"recall@5": 0.84, "citation_validity": 0.9,
                            "abstention_correctness": 0, "must_abstain_count": 1}}
    failures = gate(results, baseline)
    assert len(failures) == 3
    assert "baseline is missing" in gate(results, None)
