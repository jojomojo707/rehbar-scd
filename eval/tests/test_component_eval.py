import random

from eval.component_eval import delta, score, typo_query


def test_component_metrics_rank_and_page_matching():
    rows = [{"relevant": [{"source": "gold.pdf", "page": 4}],
             "retrieved": [{"source": "other.pdf", "page": 2}, {"source": "gold.pdf", "page": 9},
                           {"source": "gold.pdf", "page": 4}]},
            {"relevant": [], "retrieved": []}]          # must-abstain rows are skipped
    result = score(rows)
    assert result["n_answerable"] == 1
    assert result["recall@3"] == 1 and result["mrr"] == round(1 / 3, 6)
    assert 0 < result["ndcg@5"] < 1


def test_typos_are_seeded_and_keep_numbers():
    a = typo_query("What happens when a student misses attendance in 2026?", random.Random(7))
    b = typo_query("What happens when a student misses attendance in 2026?", random.Random(7))
    assert a == b and a != "What happens when a student misses attendance in 2026?"
    assert "2026" in a


def test_delta_is_noisy_minus_clean():
    clean = {"recall@3": .8, "recall@5": .9, "mrr": .7, "ndcg@5": .75}
    noisy = {"recall@3": .6, "recall@5": .9, "mrr": .5, "ndcg@5": .6}
    assert delta(clean, noisy)["recall@3"] == -0.2


def test_ndcg_never_exceeds_one_when_chunks_share_a_gold_page():
    rows = [{"relevant": [{"source": "gold.pdf", "page": 4}],
             "retrieved": [{"source": "gold.pdf", "page": 4}, {"source": "gold.pdf", "page": 4}]}]
    assert score(rows)["ndcg@5"] == 1.0
