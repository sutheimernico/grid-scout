"""Optimal day-ahead schedule for a single battery via linear programming.

Model (documented assumptions, all deliberate simplifications):
- price-taking battery on the day-ahead auction, hourly products;
- independent days: state of charge starts at 0 and any leftover energy at
  midnight is worthless (no cross-day coupling);
- round-trip efficiency split symmetrically between charge and discharge;
- at most one full cycle per day (throughput cap), no degradation model;
- no grid fees, levies or trading fees — reported revenue is gross arbitrage.

The LP is exact for this model; tests pin it to hand-computed optima.
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog


@dataclass(frozen=True)
class Battery:
    power_mw: float = 1.0
    capacity_mwh: float = 2.0
    round_trip_efficiency: float = 0.86
    cycles_per_day: float = 1.0

    @property
    def eta_one_way(self) -> float:
        return float(np.sqrt(self.round_trip_efficiency))


@dataclass(frozen=True)
class DaySchedule:
    charge_mwh: np.ndarray  # energy bought from grid per hour
    discharge_mwh: np.ndarray  # energy drawn from storage per hour
    expected_revenue: float  # against the prices used for optimization


def optimize_day(prices: np.ndarray, battery: Battery) -> DaySchedule:
    """Maximize sum(delivered_h * price_h) - sum(bought_h * price_h).

    Variables x = [c_0..c_{n-1}, d_0..d_{n-1}]; linprog minimizes, so the
    objective is negated. SoC after hour h: cumsum(c * eta_c - d) — must stay
    in [0, capacity]; delivered energy is d * eta_d.
    """
    n = len(prices)
    eta = battery.eta_one_way
    c_obj = np.concatenate([prices, -prices * eta])  # minimize: buy cost - sell revenue

    # SoC constraints via cumulative sums: L @ x <= b
    lower_tri = np.tril(np.ones((n, n)))
    # SoC_h <= capacity:  cumsum(c*eta) - cumsum(d) <= capacity
    a_upper = np.hstack([lower_tri * eta, -lower_tri])
    # SoC_h >= 0:  -cumsum(c*eta) + cumsum(d) <= 0
    a_lower = -a_upper
    # throughput cap: total stored energy <= cycles * capacity
    a_cycle = np.concatenate([np.full(n, eta), np.zeros(n)])[None, :]

    a_ub = np.vstack([a_upper, a_lower, a_cycle])
    b_ub = np.concatenate(
        [
            np.full(n, battery.capacity_mwh),
            np.zeros(n),
            [battery.cycles_per_day * battery.capacity_mwh],
        ]
    )
    bounds = [(0, battery.power_mw)] * (2 * n)

    result = linprog(c_obj, A_ub=a_ub, b_ub=b_ub, bounds=bounds, method="highs")
    if not result.success:
        raise RuntimeError(f"battery LP failed: {result.message}")
    charge, discharge = result.x[:n], result.x[n:]
    return DaySchedule(
        charge_mwh=charge,
        discharge_mwh=discharge,
        expected_revenue=float(-result.fun),
    )


def realized_revenue(schedule: DaySchedule, actual_prices: np.ndarray, battery: Battery) -> float:
    """Value of a fixed schedule at the prices that actually cleared."""
    eta = battery.eta_one_way
    delivered = schedule.discharge_mwh * eta
    return float(np.sum(delivered * actual_prices) - np.sum(schedule.charge_mwh * actual_prices))
