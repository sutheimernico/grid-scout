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
