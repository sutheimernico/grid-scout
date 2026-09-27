"""Battery sensitivity: how much of the headline depends on the battery we picked?

The headline backtest is one configuration (86% round trip, 2 h). This sweep
re-runs the identical LP backtest over a small grid of round-trip efficiency and
storage duration, on the same walk-forward year — so a reader can see whether
the forecast's value survives a better or worse battery, not just ours.

Power stays at 1 MW and the one-cycle-per-day cap stays in place, so a 4 h
battery moves twice the energy per cycle; revenue is reported per MW.
"""

import pandas as pd

from gridscout.battery.backtest import run_backtest
from gridscout.battery.schedule import Battery

EFFICIENCIES = (0.85, 0.90, 0.95)
DURATIONS_H = (2, 4)
POWER_MW = 1.0


def sweep(actual: pd.DataFrame, forecast: pd.DataFrame) -> dict:
    """actual/forecast: [local_day, hour_local, price] frames, as for run_backtest."""
    cells = []
    n_days = None
    for efficiency in EFFICIENCIES:
        for duration_h in DURATIONS_H:
            battery = Battery(
                power_mw=POWER_MW,
                capacity_mwh=POWER_MW * duration_h,
                round_trip_efficiency=efficiency,
            )
            summary = run_backtest(actual, forecast, battery).summary
            n_days = summary["n_days"]
            cells.append(
                {
                    "round_trip_efficiency": efficiency,
                    "duration_h": duration_h,
                    "capacity_mwh": battery.capacity_mwh,
                    "revenue_eur": summary["revenue_eur"],
                    "revenue_eur_per_mw_year": summary["revenue_eur_per_mw_year"],
                    "capture_rate_model": summary["capture_rate_model"],
                    "capture_rate_naive": summary["capture_rate_naive"],
                    "model_edge_over_naive_eur_per_mw_year": round(
                        summary["revenue_eur_per_mw_year"]["model"]
                        - summary["revenue_eur_per_mw_year"]["naive"],
                        2,
                    ),
                }
            )
    return {
        "power_mw": POWER_MW,
        "cycles_per_day": Battery().cycles_per_day,
        "n_days": n_days,
        "grid": {"round_trip_efficiency": list(EFFICIENCIES), "duration_h": list(DURATIONS_H)},
        "cells": cells,
    }
