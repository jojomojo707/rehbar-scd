from eval.component_eval import score


def test_component_metrics_and_irrelevant_prefix_stress():
    rows = [{"relevant": [{"source": "gold.pdf", "page": 4}],
             "retrieved": [{"source": "other.pdf", "page": 2},
                           {"source": "gold.pdf", "page": 4}]}]
    baseline = score(rows)
    noisy = score(rows, noise=True)
    assert baseline["recall@5"] == 1
    assert baseline["mrr"] == .5
    assert noisy["recall@3"] == 0
