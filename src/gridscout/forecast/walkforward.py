"""Expanding-window walk-forward evaluation over local days.

Splits by Europe/Berlin calendar day so a fold never cuts through a delivery
day. Models are refit every `step_days` (weekly by default) on all data up to
the fold boundary — no shuffling, no random splits, time only moves forward.
"""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from gridscout.forecast.features import feature_columns


@dataclass(frozen=True)
class Fold:
    train_days: tuple[date, ...]
    test_days: tuple[date, ...]


def make_folds(days: list[date], min_train_days: int, step_days: int = 7) -> list[Fold]:
    """Expanding folds: train on days[:k], test on the next step_days block."""
    folds = []
    k = min_train_days
    while k < len(days):
        test = days[k : k + step_days]
        folds.append(Fold(train_days=tuple(days[:k]), test_days=tuple(test)))
        k += step_days
    return folds


def run_walkforward(matrix: pd.DataFrame, model, folds: list[Fold]) -> pd.DataFrame:
    """Fit/predict per fold; returns rows of the test period with predictions."""
    cols = feature_columns(matrix)
    results = []
    for fold in folds:
        train = matrix[matrix["local_day"].isin(fold.train_days)]
        test = matrix[matrix["local_day"].isin(fold.test_days)]
        if train.empty or test.empty:
            continue
        model.fit(train[cols], train["target"])
        pred = model.predict(test[cols])
        results.append(
            pd.DataFrame(
                {
                    "prediction": np.asarray(pred),
                    "target": test["target"].to_numpy(),
                    "local_day": test["local_day"].to_numpy(),
                    "hour_local": test["hour_local"].to_numpy(),
                },
                index=test.index,
            )
        )
    if not results:
        raise ValueError("no folds produced results — not enough data?")
    return pd.concat(results)
