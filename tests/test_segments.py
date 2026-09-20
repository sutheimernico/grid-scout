from datetime import date

import pandas as pd
import pytest

from gridscout.forecast.segments import segment_errors


def frame(rows):
    """rows: (day, hour, target, pred_point, pred_naive, pred_snaive7)"""
    return pd.DataFrame(
        rows,
        columns=["local_day", "hour_local", "target", "pred_point", "pred_naive", "pred_snaive7"],
    )


def test_hand_computed_segment_errors():
    # hour 0: model off by 1, naive off by 3 -> model wins
    # hour 1: model off by 4, naive off by 2 -> naive wins
    rows = []
    for day in (date(2026, 9, 14), date(2026, 9, 15)):
        rows.append((day, 0, 100.0, 101.0, 103.0, 110.0))
        rows.append((day, 1, 50.0, 54.0, 52.0, 60.0))
    segments = segment_errors(frame(rows))

    by_hour = {s["segment"]: s for s in segments["by_hour"]}
    assert by_hour["00:00"] == {
        "segment": "00:00",
        "n": 2,
        "mae_model": 1.0,
        "mae_naive": 3.0,
        "mae_snaive7": 10.0,
        "skill_vs_naive_pct": 66.7,
        "best": "model",
    }
    assert by_hour["01:00"]["best"] == "naive"
    assert by_hour["01:00"]["skill_vs_naive_pct"] == -100.0
    assert segments["overall"]["mae_model"] == 2.5
    assert segments["n_hours"] == 4


def test_weekday_labels_follow_the_calendar():
    rows = [(date(2026, 9, 14), 0, 10.0, 10.0, 10.0, 10.0)]  # a Monday
    rows += [(date(2026, 9, 20), 0, 10.0, 10.0, 10.0, 10.0)]  # a Sunday
    segments = segment_errors(frame(rows))
    assert [s["segment"] for s in segments["by_weekday"]] == ["Mon", "Sun"]


def test_negative_hours_and_volatile_days_are_separated():
    rows = []
    # nine calm days
    for d in range(1, 10):
        for hour in range(4):
            rows.append((date(2026, 9, d), hour, 50.0 + hour, 50.0, 50.0, 50.0))
    # one wild day with a negative hour
    rows.append((date(2026, 9, 10), 0, -30.0, 0.0, 0.0, 0.0))
    for hour in (1, 2, 3):
        rows.append((date(2026, 9, 10), hour, 300.0, 250.0, 200.0, 100.0))

    segments = segment_errors(frame(rows))
    by_regime = {s["segment"]: s for s in segments["by_regime"]}
    assert by_regime["negative prices"]["n"] == 1
    # the wild day's remaining hours land in the top-decile spread bucket
    assert by_regime["volatile days"]["n"] == 3
    assert by_regime["normal"]["n"] == 36
    assert set(segments["definitions"]) == {"negative prices", "volatile days", "normal"}


def test_string_days_from_parquet_are_accepted():
    rows = [("2026-09-14", 0, 10.0, 11.0, 13.0, 20.0)]
    assert segment_errors(frame(rows))["by_weekday"][0]["segment"] == "Mon"


def test_missing_columns_are_named():
    with pytest.raises(ValueError, match="pred_snaive7"):
        segment_errors(pd.DataFrame({"local_day": [], "hour_local": [], "target": []}))
