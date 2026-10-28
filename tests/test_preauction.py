"""Pins the availability claims behind the forecast to publication times.

The backtest's FULL feature set reads SMARD's generation forecast *for* the
delivery day; SMARD only publishes it 17-21 UTC on D-1 (measured, see
forecast/forward.py), after the 12:00 auction. These tests make that explicit:
PRE_AUCTION must be fully published before gate closure, FULL must not be.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from gridscout.forecast.conformal import conformalize
from gridscout.forecast.features import FULL, PRE_AUCTION, FeatureSet
from gridscout.forecast.forward import gate_closure_utc
from gridscout.forecast.models import RidgePerHour
from tests.test_features import build_matrix, synthetic_raw


def day_start(day: date) -> pd.Timestamp:
    return pd.Timestamp(day, tz="Europe/Berlin").tz_convert("UTC")


def published_at(series: str, day: date) -> pd.Timestamp:
    """Latest moment the values dated `day` are on SMARD (conservative, measured)."""
    if series == "price_day_ahead":
        return gate_closure_utc(day)  # cleared at 12:00 Berlin on the day before
    if series.startswith("forecast_"):
        # republished for day d only 17-21 UTC on d-1; 1 h before d's midnight is
        # >= 21:00 UTC in both summer and winter time
        return day_start(day) - pd.Timedelta(hours=1)
    return day_start(day + timedelta(days=1)) + pd.Timedelta(hours=6)  # realized values


def inputs_by_target_day(features: FeatureSet) -> list[tuple[str, int]]:
    """(series, lag in days) for every raw input; day-ahead series have lag 0."""
    pairs = [(features.target, lag) for lag in features.price_lag_days]
    pairs += [(name, lag) for name, lags in features.lagged_series for lag in lags]
    pairs += [(name, 0) for name in features.day_ahead_series]
    return pairs


def latest_publication_for(features: FeatureSet, target_day: date) -> pd.Timestamp:
    return max(
        published_at(series, target_day - timedelta(days=lag))
        for series, lag in inputs_by_target_day(features)
    )


def test_pre_auction_inputs_are_published_before_gate_closure():
    for day in (date(2026, 1, 15), date(2026, 7, 15), date(2026, 10, 26)):
        assert latest_publication_for(PRE_AUCTION, day) <= gate_closure_utc(day), day


def test_full_feature_set_is_not_pre_auction():
    """The backtest assumption, stated as a test: TSO forecasts for day D come
    after the auction on a SMARD-only feed."""
    day = date(2026, 7, 15)
    assert latest_publication_for(FULL, day) > gate_closure_utc(day)


def test_pre_auction_has_no_delivery_day_inputs():
    assert PRE_AUCTION.day_ahead_series == ()
    assert all(lag >= 1 for _, lag in inputs_by_target_day(PRE_AUCTION))


def test_pre_auction_matrix_ignores_delivery_day_values():
    raw = synthetic_raw(days=30)
    day = date(2024, 1, 20)
    rows = raw.index.tz_convert("Europe/Berlin").date >= day
    poisoned = raw.copy()
    poisoned.loc[rows, :] = 9_999.0
    clean = build_matrix(raw, features=PRE_AUCTION)
    dirty = build_matrix(poisoned, features=PRE_AUCTION)
    mask = clean["local_day"] == day
    cols = [c for c in clean.columns if c not in ("target", "local_day")]
    pd.testing.assert_frame_equal(clean.loc[mask, cols], dirty.loc[mask, cols])


class TestRidgePerHour:
    def test_recovers_a_linear_signal_per_hour(self):
        matrix = build_matrix(synthetic_raw(days=60))
        X = matrix.drop(columns=["target", "local_day"])
        y = 2.0 * X["price_lag_1d"] + X["hour_local"]
        model = RidgePerHour(alpha=1e-6)
        model.fit(X, y)
        assert np.allclose(model.predict(X), y, atol=1e-3)


class TestConformal:
    def _frame(self, days: int, width: float) -> pd.DataFrame:
        rng = np.random.default_rng(0)
        n = days * 24
        target = rng.normal(0, 10, n)
        return pd.DataFrame(
            {
                "target": target,
                "pred_q10": np.full(n, -width),
                "pred_q90": np.full(n, width),
                "local_day": np.repeat(np.arange(days), 24),
            }
        )

    def test_widens_a_too_narrow_band_to_target_coverage(self):
        out = conformalize(self._frame(120, width=3.0), alpha=0.2)
        scored = out.dropna(subset=["q_low_cal"])
        inside = (scored["target"] >= scored["q_low_cal"]) & (
            scored["target"] <= scored["q_high_cal"]
        )
        cov = inside.mean()
        assert 0.75 < cov < 0.86
        assert (scored["q_high_cal"] - scored["q_low_cal"]).mean() > 6.0

    def test_early_blocks_without_history_stay_uncalibrated(self):
        out = conformalize(self._frame(60, width=3.0), alpha=0.2, min_calib_blocks=4)
        assert out.loc[out["local_day"] < 28, "q_low_cal"].isna().all()

    def test_calibration_uses_only_earlier_blocks(self):
        frame = self._frame(60, width=3.0)
        base = conformalize(frame, alpha=0.2)
        changed = frame.copy()
        last_block = changed["local_day"] >= 56
        changed.loc[last_block, "target"] = 1e6  # future outcome must not leak backwards
        again = conformalize(changed, alpha=0.2)
        pd.testing.assert_series_equal(
            base.loc[~last_block, "q_low_cal"], again.loc[~last_block, "q_low_cal"]
        )
