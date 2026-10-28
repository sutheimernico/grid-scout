"""Forecast models behind one minimal interface: fit(X, y) / predict(X).

Baselines are real models here on purpose — they run through the identical
walk-forward machinery as LightGBM, so their numbers are comparable by
construction, not by promise.
"""

from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd


class NaiveYesterday:
    """price(D, h) := price(D-1, h) — known at gate closure."""

    name = "naive_yesterday"

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        pass

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return X["price_lag_1d"].to_numpy()


class SeasonalNaiveWeek:
    """price(D, h) := price(D-7, h) — same weekday one week earlier."""

    name = "seasonal_naive_7d"

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        pass

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return X["price_lag_7d"].to_numpy()


@dataclass
class LightGBMPrice:
    """Gradient-boosted point forecast (L1 objective — MAE-optimal, robust to
    price spikes) or quantile forecast when `quantile` is set."""

    quantile: float | None = None
    n_estimators: int = 600
    learning_rate: float = 0.05
    num_leaves: int = 63
    seed: int = 42
    # Pinned, not left to LightGBM's "all cores" default: unbounded OpenMP threads
    # oversubscribe small CI/test machines (a test run hung for >10 min) and make
    # run time depend on the host. Fixed count + deterministic=True keeps results
    # reproducible.
    num_threads: int = 4
    name: str = field(init=False)
    _booster: lgb.Booster | None = field(init=False, default=None, repr=False)

    def __post_init__(self):
        self.name = "lgbm_point" if self.quantile is None else f"lgbm_q{int(self.quantile * 100)}"

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        params = {
            "objective": "regression_l1" if self.quantile is None else "quantile",
            "learning_rate": self.learning_rate,
            "num_leaves": self.num_leaves,
            "seed": self.seed,
            "num_threads": self.num_threads,
            "deterministic": True,
            "force_row_wise": True,
            "verbosity": -1,
        }
        if self.quantile is not None:
            params["alpha"] = self.quantile
        train_set = lgb.Dataset(X, label=y)
        self._booster = lgb.train(params, train_set, num_boost_round=self.n_estimators)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self._booster is None:
            raise RuntimeError("model not fitted")
        return np.asarray(self._booster.predict(X))


class RidgePerHour:
    """LEAR-style linear baseline: one ridge regression per local hour.

    The standard strong benchmark in day-ahead price forecasting (Lago et al.):
    each hour of the day gets its own linear model on the same inputs LightGBM
    sees, so any gap to it is the value of non-linearity, not of information.
    Closed-form ridge on standardised features; `hour_local` selects the model
    and `month` is left out (a linear month index is meaningless).
    """

    name = "ridge_per_hour"

    def __init__(self, alpha: float = 10.0):
        self.alpha = alpha
        self._coef: dict[int, tuple[list[str], np.ndarray, np.ndarray, np.ndarray, float]] = {}

    @staticmethod
    def _inputs(X: pd.DataFrame) -> list[str]:
        return [c for c in X.columns if c not in ("hour_local", "month")]

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        cols = self._inputs(X)
        self._coef = {}
        for hour, rows in X.groupby("hour_local").groups.items():
            A = X.loc[rows, cols].to_numpy(dtype=float)
            t = y.loc[rows].to_numpy(dtype=float)
            mean, std = A.mean(axis=0), A.std(axis=0)
            std[std == 0] = 1.0
            Z = (A - mean) / std
            t_mean = t.mean()
            beta = np.linalg.solve(Z.T @ Z + self.alpha * np.eye(len(cols)), Z.T @ (t - t_mean))
            self._coef[int(hour)] = (cols, mean, std, beta, t_mean)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if not self._coef:
            raise RuntimeError("model not fitted")
        out = np.empty(len(X))
        hours = X["hour_local"].to_numpy()
        for hour, (cols, mean, std, beta, t_mean) in self._coef.items():
            mask = hours == hour
            if mask.any():
                Z = (X.loc[mask, cols].to_numpy(dtype=float) - mean) / std
                out[mask] = Z @ beta + t_mean
        return out
