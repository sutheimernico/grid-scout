from datetime import date

import numpy as np
import pandas as pd
import pytest

from gridscout.forecast.features import (
    DAY_AHEAD_SERIES,
    TARGET,
    build_matrix,
    feature_columns,
    local_days,
)

REALIZED = ["load"]


def synthetic_raw(days: int = 30, start: str = "2024-01-01") -> pd.DataFrame:
    """Deterministic hourly frame covering all series the matrix needs."""
    idx = pd.date_range(start=start, periods=days * 24, freq="h", tz="Europe/Berlin").tz_convert(
        "UTC"
    )
    rng = np.random.default_rng(7)
    data = {TARGET: rng.normal(100, 30, len(idx))}
    for name in DAY_AHEAD_SERIES + REALIZED:
        data[name] = rng.uniform(0, 50_000, len(idx))
    return pd.DataFrame(data, index=idx)


def test_lags_are_exact_24h_multiples():
    raw = synthetic_raw()
    matrix = build_matrix(raw)
    ts = matrix.index[100]
    assert matrix.loc[ts, "price_lag_1d"] == raw.loc[ts - pd.Timedelta(days=1), TARGET]
    assert matrix.loc[ts, "price_lag_7d"] == raw.loc[ts - pd.Timedelta(days=7), TARGET]
    assert matrix.loc[ts, "load_lag_2d"] == raw.loc[ts - pd.Timedelta(days=2), "load"]


def test_first_week_dropped_for_lags():
    raw = synthetic_raw()
    matrix = build_matrix(raw)
    assert matrix.index.min() >= raw.index.min() + pd.Timedelta(days=7)


def test_calendar_features():
    raw = synthetic_raw(days=10, start="2024-01-01")
    matrix = build_matrix(raw)
    jan8 = matrix[matrix["local_day"] == date(2024, 1, 8)]  # a Monday
    assert (jan8["day_of_week"] == 0).all()
    assert (jan8["is_weekend"] == 0).all()
    assert set(jan8["hour_local"]) == set(range(24))


def test_holiday_flag():
    # need lag warm-up before Jan 1: start in December
    raw = synthetic_raw(days=40, start="2023-12-01")
    matrix = build_matrix(raw)
    new_year = matrix[matrix["local_day"] == date(2024, 1, 1)]
    boxing_day_ish = matrix[matrix["local_day"] == date(2024, 1, 2)]
    assert (new_year["is_holiday"] == 1).all()
    assert (boxing_day_ish["is_holiday"] == 0).all()


@pytest.mark.parametrize("series", [TARGET, "load"])
def test_no_leakage_from_target_day_realizations(series):
    """Perturbing realized values ON day D must not move day-D features."""
    raw = synthetic_raw()
    day = date(2024, 1, 20)
    day_rows = raw.index.tz_convert("Europe/Berlin").date == day

    baseline = build_matrix(raw)
    perturbed_raw = raw.copy()
    perturbed_raw.loc[day_rows, series] = 9_999.0
    perturbed = build_matrix(perturbed_raw)

    cols = [c for c in feature_columns(baseline)]
    day_mask = baseline["local_day"] == day
    pd.testing.assert_frame_equal(baseline.loc[day_mask, cols], perturbed.loc[day_mask, cols])


def test_day_ahead_forecasts_do_flow_into_target_day():
    """The published forecasts FOR day D are legitimate day-D features."""
    raw = synthetic_raw()
    day = date(2024, 1, 20)
    day_rows = raw.index.tz_convert("Europe/Berlin").date == day

    baseline = build_matrix(raw)
    perturbed_raw = raw.copy()
    perturbed_raw.loc[day_rows, "forecast_solar"] = 12_345.0
    perturbed = build_matrix(perturbed_raw)

    day_mask = baseline["local_day"] == day
    assert (perturbed.loc[day_mask, "forecast_solar"] == 12_345.0).all()
    assert not baseline.loc[day_mask, "forecast_solar"].eq(12_345.0).any()


def test_local_days_sorted_and_complete():
    raw = synthetic_raw(days=20)
    days = local_days(build_matrix(raw))
    assert days == sorted(days)
    assert len(days) >= 12  # 20 days minus 7 lag warm-up, minus edge partials
