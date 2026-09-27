from datetime import date

import numpy as np
import pandas as pd
import pytest

from gridscout.battery.backtest import frames_from_predictions, run_backtest
from gridscout.battery.schedule import Battery
from gridscout.battery.sensitivity import DURATIONS_H, EFFICIENCIES, sweep

# Four cheap hours, then four expensive ones. With 1 MW power every cell's
# optimum can be written down by hand (see test_perfect_revenue_is_hand_computed).
DAY = [10.0] * 4 + [100.0] * 4


def predictions(days: dict[date, list[float]], forecast: dict[date, list[float]]) -> pd.DataFrame:
    rows = [
        {"local_day": day, "hour_local": h, "target": p, "pred_point": forecast[day][h]}
        for day, prices in days.items()
        for h, p in enumerate(prices)
    ]
    return pd.DataFrame(rows)


def hand_optimum(efficiency: float, duration_h: int) -> float:
    """1 MW battery on DAY, one cycle, one-way efficiency sqrt(round trip).

    2h: the 2 MWh storage limit binds — buy 2/eta, deliver 2*eta.
    4h: the 4 cheap hours at 1 MW bind — buy 4, store 4*eta, deliver 4*eta^2.
    """
    eta = np.sqrt(efficiency)
    if duration_h == 2:
        return 100 * 2 * eta - 10 * 2 / eta
    return 100 * 4 * efficiency - 10 * 4


class TestSweep:
    def test_grid_is_the_documented_six_cells(self):
        frame = predictions(
            {date(2025, 1, 1): DAY, date(2025, 1, 2): DAY},
            {date(2025, 1, 1): DAY, date(2025, 1, 2): DAY},
        )
        result = sweep(*frames_from_predictions(frame))
        cells = {(c["round_trip_efficiency"], c["duration_h"]) for c in result["cells"]}
        assert EFFICIENCIES == (0.85, 0.90, 0.95)
        assert DURATIONS_H == (2, 4)
        assert cells == {(e, d) for e in EFFICIENCIES for d in DURATIONS_H}
        assert result["n_days"] == 1  # day 1 has no predecessor for the naive schedule

    def test_perfect_revenue_is_hand_computed(self):
        frame = predictions(
            {date(2025, 1, 1): DAY, date(2025, 1, 2): DAY},
            {date(2025, 1, 1): DAY, date(2025, 1, 2): DAY},
        )
        result = sweep(*frames_from_predictions(frame))
        for cell in result["cells"]:
            expected = hand_optimum(cell["round_trip_efficiency"], cell["duration_h"])
            assert cell["revenue_eur"]["perfect"] == pytest.approx(expected, abs=0.01)
            # a perfect forecast captures everything, and so does naive on a repeated day
            assert cell["capture_rate_model"] == pytest.approx(1.0, abs=1e-4)
            assert cell["capture_rate_naive"] == pytest.approx(1.0, abs=1e-4)

    def test_cells_reproduce_the_single_backtest(self):
        # Irregular prices and a noisy forecast, so model, naive and perfect differ.
        rng = np.random.default_rng(7)
        days = {date(2025, 3, d): list(rng.uniform(-20, 150, 24)) for d in range(1, 6)}
        forecast = {d: list(np.array(p) + rng.normal(0, 25, 24)) for d, p in days.items()}
        actual, model = frames_from_predictions(predictions(days, forecast))
        result = sweep(actual, model)
        for cell in result["cells"]:
            battery = Battery(
                power_mw=1.0,
                capacity_mwh=cell["duration_h"],
                round_trip_efficiency=cell["round_trip_efficiency"],
            )
            single = run_backtest(actual, model, battery).summary
            assert cell["revenue_eur"] == single["revenue_eur"]
            assert cell["revenue_eur_per_mw_year"] == single["revenue_eur_per_mw_year"]
            assert cell["capture_rate_model"] == single["capture_rate_model"]

    def test_more_efficiency_and_more_storage_never_earn_less(self):
        frame = predictions(
            {date(2025, 1, 1): DAY, date(2025, 1, 2): DAY},
            {date(2025, 1, 1): DAY, date(2025, 1, 2): DAY},
        )
        cells = {
            (c["round_trip_efficiency"], c["duration_h"]): c["revenue_eur"]["perfect"]
            for c in sweep(*frames_from_predictions(frame))["cells"]
        }
        for d in DURATIONS_H:
            assert cells[(0.85, d)] < cells[(0.90, d)] < cells[(0.95, d)]
        for e in EFFICIENCIES:
            assert cells[(e, 2)] < cells[(e, 4)]
