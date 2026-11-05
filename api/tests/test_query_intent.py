from app.services.query_intent import classify_query


def test_explicit_year_requests_historical_versions() -> None:
    intent = classify_query("What changed in August 2023?")
    assert intent.include_superseded is True
    assert intent.requested_year == "2023"


def test_current_query_excludes_superseded_by_default() -> None:
    intent = classify_query("What is the attendance requirement?")
    assert intent.include_superseded is False
    assert intent.requested_year is None


def test_old_policy_cue_requests_superseded_versions() -> None:
    assert classify_query("What did the previous policy say?").include_superseded
