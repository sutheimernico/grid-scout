from datetime import date

import numpy as np
import pandas as pd
import pytest

from gridscout.battery.backtest import run_backtest
from gridscout.battery.schedule import Battery, DaySchedule, optimize_day, realized_revenue

LOSSLESS = Battery(power_mw=1.0, capacity_mwh=2.0, round_trip_efficiency=1.0)


class TestOptimizeDay:
    def test_hand_computed_lossless_optimum(self):
        # cheap hours 0,1 (10, 20), expensive hours 2,3 (100, 90); 1 MW / 2 MWh:
        # buy 1 MWh at 10 and 1 at 20, sell 1 at 100 and 1 at 90 -> 160
        prices = np.array([10.0, 20.0, 100.0, 90.0])
        schedule = optimize_day(prices, LOSSLESS)
        assert schedule.expected_revenue == pytest.approx(160.0, abs=1e-6)
        assert schedule.charge_mwh[:2] == pytest.approx([1.0, 1.0], abs=1e-6)
        assert schedule.discharge_mwh[2:] == pytest.approx([1.0, 1.0], abs=1e-6)

    def test_cannot_discharge_before_charging(self):
        # expensive hour comes FIRST -> nothing to sell, best is doing nothing
        prices = np.array([100.0, 10.0])
        schedule = optimize_day(prices, LOSSLESS)
        assert schedule.expected_revenue == pytest.approx(0.0, abs=1e-6)

    def test_flat_prices_no_trade_with_losses(self):
        prices = np.full(24, 80.0)
        schedule = optimize_day(prices, Battery())
        assert schedule.expected_revenue == pytest.approx(0.0, abs=1e-6)

    def test_negative_prices_get_paid_to_charge(self):
        prices = np.array([-50.0, 60.0])
        schedule = optimize_day(prices, LOSSLESS)
        # buy 1 MWh at -50 (earn 50), sell at 60 -> 110
        assert schedule.expected_revenue == pytest.approx(110.0, abs=1e-6)

    def test_cycle_limit_binds(self):
        # two spreads available but only one cycle (2 MWh) allowed
        prices = np.array([10.0, 100.0, 10.0, 100.0])
        schedule = optimize_day(prices, LOSSLESS)
        assert float(schedule.charge_mwh.sum()) == pytest.approx(2.0, abs=1e-6)

    def test_efficiency_reduces_revenue(self):
        prices = np.array([10.0, 20.0, 100.0, 90.0])
        lossy = optimize_day(prices, Battery(round_trip_efficiency=0.86))
        assert lossy.expected_revenue < 160.0

    def test_dst_day_lengths_supported(self):
        for n in (23, 24, 25):
            prices = np.linspace(10, 100, n)
            assert optimize_day(prices, Battery()).expected_revenue >= 0

    def test_realized_revenue_uses_actual_prices(self):
        planned = DaySchedule(
            charge_mwh=np.array([1.0, 0.0]),
            discharge_mwh=np.array([0.0, 1.0]),
            expected_revenue=90.0,
        )
        # forecast promised a spread, reality collapsed it
        actual = np.array([50.0, 50.0])
        assert realized_revenue(planned, actual, LOSSLESS) == pytest.approx(0.0)


def price_frame(days: dict[date, list[float]]) -> pd.DataFrame:
    rows = [
        {"local_day": day, "hour_local": h, "price": p}
        for day, prices in days.items()
        for h, p in enumerate(prices)
    ]
    return pd.DataFrame(rows)


class TestBacktest:
    def test_perfect_forecast_reaches_capture_rate_1(self):
        days = {
            date(2025, 1, 1): [10.0, 20.0, 100.0, 90.0],
            date(2025, 1, 2): [30.0, 10.0, 80.0, 120.0],
            date(2025, 1, 3): [10.0, 5.0, 90.0, 70.0],
        }
        actual = price_frame(days)
        result = run_backtest(actual, forecast=actual, battery=LOSSLESS)
        # day 1 has no predecessor for the naive schedule -> 2 evaluated days
        assert len(result.daily) == 2
        assert result.summary["capture_rate_model"] == pytest.approx(1.0, abs=1e-9)

    def test_bad_forecast_underperforms_naive(self):
        actual = price_frame(
            {
                date(2025, 1, 1): [10.0, 20.0, 100.0, 90.0],
                date(2025, 1, 2): [10.0, 20.0, 100.0, 90.0],  # like yesterday
            }
        )
        inverted = price_frame(
            {
                date(2025, 1, 2): [100.0, 90.0, 10.0, 20.0],  # forecast upside down
            }
        )
        result = run_backtest(actual, forecast=inverted, battery=LOSSLESS)
        assert result.summary["revenue_eur"]["naive"] > result.summary["revenue_eur"]["model"]
        assert result.summary["revenue_eur"]["model"] < 0  # trades against the spread

    def test_missing_forecast_days_are_skipped_and_counted(self):
        actual = price_frame(
            {
                date(2025, 1, 1): [10.0, 100.0],
                date(2025, 1, 2): [10.0, 100.0],
                date(2025, 1, 3): [10.0, 100.0],
            }
        )
        forecast = price_frame({date(2025, 1, 2): [10.0, 100.0]})
        result = run_backtest(actual, forecast, battery=LOSSLESS)
        assert len(result.daily) == 1
        assert result.summary["skipped_days"] == 2  # day 1 (no prev), day 3 (no forecast)
