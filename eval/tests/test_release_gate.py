from pathlib import Path

from eval.release_gate import DEFAULTS, evaluate, thresholds


def suite(recall5: float, faith: float | None, p95: float, abstain: float) -> dict:
    return {"mean": {"component": {"recall@5": recall5},
                     "end_to_end": {"faithfulness": faith, "latency_p95_seconds": p95,
                                    "abstention_correctness": abstain}}}


def test_candidate_meeting_all_release_limits_passes() -> None:
    assert evaluate(suite(.81, .95, 8.0, 1.0), suite(.82, .9, 7.0, 1.0), DEFAULTS) == []


def test_regression_in_each_gated_dimension_is_reported() -> None:
    failures = evaluate(suite(.70, .5, 30.0, .8), suite(.82, .9, 7.0, 1.0), DEFAULTS)
    assert len(failures) == 4
    for word in ("recall@5", "faithfulness", "p95 latency", "abstention"):
        assert any(word in failure for failure in failures)


def test_missing_judgements_fail_closed() -> None:
    failures = evaluate(suite(.82, None, 8.0, 1.0), suite(.82, .9, 7.0, 1.0), DEFAULTS)
    assert failures == ["faithfulness: the candidate run has no judged answers"]


def test_thresholds_are_read_from_a_mounted_configmap_directory(tmp_path: Path) -> None:
    (tmp_path / "MAX_P95_SECONDS").write_text("0.5\n")
    limits = thresholds(tmp_path)
    assert limits["MAX_P95_SECONDS"] == 0.5
    assert limits["MAX_RECALL5_DROP"] == DEFAULTS["MAX_RECALL5_DROP"]
    assert evaluate(suite(.82, .95, 8.0, 1.0), suite(.82, .9, 7.0, 1.0), limits) == [
        "p95 latency 8.00s exceeds the maximum 0.50s"]
