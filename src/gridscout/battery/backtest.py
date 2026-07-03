"""Battery arbitrage backtest: what is the price forecast worth in EUR?

Three schedules per delivery day, all evaluated at ACTUAL cleared prices:
- perfect:  optimized on actual prices (upper bound, not tradable);
- model:    optimized on the model's price forecast;
- naive:    optimized on yesterday's prices (the free alternative).

capture_rate = model_revenue / perfect_revenue. The interesting number is the
gap between model and naive — that gap is the economic value of the forecast.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from gridscout.battery.schedule import Battery, optimize_day, realized_revenue


@dataclass
class BacktestResult:
    battery: Battery
    daily: pd.DataFrame  # columns: local_day, perfect, model, naive
    summary: dict = field(init=False)

    def __post_init__(self):
        totals = self.daily[["perfect", "model", "naive"]].sum()
        n_days = len(self.daily)
        annualize = 365.0 / n_days if n_days else float("nan")
        self.summary = {
            "n_days": n_days,
            "revenue_eur": {k: round(float(v), 2) for k, v in totals.items()},
            "revenue_eur_per_mw_year": {
                k: round(float(v) * annualize / self.battery.power_mw, 2) for k, v in totals.items()
            },
            "capture_rate_model": round(float(totals["model"] / totals["perfect"]), 4),
            "capture_rate_naive": round(float(totals["naive"] / totals["perfect"]), 4),
            "model_edge_over_naive_eur": round(float(totals["model"] - totals["naive"]), 2),
        }


def run_backtest(
    actual: pd.DataFrame, forecast: pd.DataFrame, battery: Battery | None = None
) -> BacktestResult:
    """actual/forecast: frames with columns [local_day, hour_local, price].

    Days are used only when both frames have the identical full set of hours
    for that day (23/24/25 with DST) AND the previous day exists in `actual`
    (the naive schedule needs it). Skipped days are counted, not hidden.
    """
    battery = battery or Battery()
    actual_days = _by_day(actual)
    forecast_days = _by_day(forecast)

    rows = []
    skipped = 0
    for day, actual_prices in sorted(actual_days.items()):
        prev = _previous_day(actual_days, day)
        model_prices = forecast_days.get(day)
        if model_prices is None or prev is None or len(model_prices) != len(actual_prices):
            skipped += 1
            continue
        naive_prices = prev if len(prev) == len(actual_prices) else prev[: len(actual_prices)]
        if len(naive_prices) < len(actual_prices):
            naive_prices = np.pad(naive_prices, (0, len(actual_prices) - len(naive_prices)), "edge")
        rows.append(
            {
                "local_day": day,
                "perfect": optimize_day(actual_prices, battery).expected_revenue,
                "model": realized_revenue(
                    optimize_day(model_prices, battery), actual_prices, battery
                ),
                "naive": realized_revenue(
                    optimize_day(naive_prices, battery), actual_prices, battery
                ),
            }
        )
    if not rows:
        raise ValueError("no overlapping days between actual and forecast prices")
    result = BacktestResult(battery=battery, daily=pd.DataFrame(rows))
    result.summary["skipped_days"] = skipped
    return result


def _by_day(frame: pd.DataFrame) -> dict[date, np.ndarray]:
    return {
        day: g.sort_values("hour_local")["price"].to_numpy()
        for day, g in frame.groupby("local_day")
    }


def _previous_day(days: dict[date, np.ndarray], day: date) -> np.ndarray | None:
    return days.get(day - timedelta(days=1))
