from eval.release_gate import DEFAULTS, evaluate


def test_candidate_meeting_all_release_limits_passes() -> None:
    candidate = {"recall@5": .92, "abstention_correctness": 1.0,
                 "latency_p95_seconds": 11.0}
    baseline = {"recall@5": .94, "abstention_correctness": 1.0}
    faithfulness = {"score": .95}
    assert evaluate(candidate, baseline, faithfulness, DEFAULTS) == []


def test_regression_in_each_gated_dimension_is_reported() -> None:
    candidate = {"recall@5": .58, "abstention_correctness": .5,
                 "latency_p95_seconds": 20.0}
    baseline = {"recall@5": .94, "abstention_correctness": 1.0}
    failures = evaluate(candidate, baseline, {"score": .5}, DEFAULTS)
    assert len(failures) == 4
    assert any("recall@5" in failure for failure in failures)
    assert any("faithfulness" in failure for failure in failures)
    assert any("p95 latency" in failure for failure in failures)
    assert any("abstention" in failure for failure in failures)
