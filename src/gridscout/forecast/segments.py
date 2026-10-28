"""Segmented error analysis: where the model wins, and where it does not.

An aggregate MAE hides the interesting part. The walk-forward predictions are
already stored per hour, so slicing them by hour of day, weekday and price
regime costs nothing — and the segments where a naive baseline still wins are
the ones worth showing.
"""

from datetime import date

import numpy as np
import pandas as pd

from gridscout.forecast.metrics import mae

MODEL_COLUMNS = {
    "model": "pred_point",
    "naive": "pred_naive",
    "snaive7": "pred_snaive7",
}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
#: Days whose intraday price spread is in the top decile.
VOLATILE_QUANTILE = 0.9


def segment_errors(predictions: pd.DataFrame) -> dict:
    """predictions: the walk-forward frame (local_day, hour_local, target, pred_*)."""
    missing = [
        c
        for c in ("local_day", "hour_local", "target", *MODEL_COLUMNS.values())
        if c not in predictions
    ]
    if missing:
        raise ValueError(f"predictions frame is missing columns: {missing}")
    frame = predictions.copy()
    frame["local_day"] = frame["local_day"].map(_as_date)
    frame["weekday"] = frame["local_day"].map(lambda d: WEEKDAYS[d.weekday()])
    frame["regime"] = _price_regime(frame)

    return {
        "n_hours": int(len(frame)),
        "overall": _errors(frame),
        "by_hour": [
            {"segment": f"{hour:02d}:00", **_errors(group)}
            for hour, group in frame.groupby("hour_local", sort=True)
        ],
        "by_weekday": [
            {"segment": day, **_errors(frame[frame["weekday"] == day])}
            for day in WEEKDAYS
            if (frame["weekday"] == day).any()
        ],
        "by_regime": [
            {"segment": regime, **_errors(frame[frame["regime"] == regime])}
            for regime in ("negative prices", "volatile days", "normal")
            if (frame["regime"] == regime).any()
        ],
        "definitions": {
            "negative prices": "hours that cleared below 0 EUR/MWh",
            "volatile days": (
                "days whose intraday price spread is in the top decile of the eval period"
            ),
            "normal": "everything else",
        },
    }


def _errors(group: pd.DataFrame) -> dict:
    truth = group["target"].to_numpy()
    errors = {name: mae(truth, group[col].to_numpy()) for name, col in MODEL_COLUMNS.items()}
    best = min(errors, key=errors.get)
    return {
        "n": int(len(group)),
        "mae_model": round(errors["model"], 2),
        "mae_naive": round(errors["naive"], 2),
        "mae_snaive7": round(errors["snaive7"], 2),
        "skill_vs_naive_pct": (
            round(100 * (1 - errors["model"] / errors["naive"]), 1) if errors["naive"] else None
        ),
        "best": best,
    }


def _price_regime(frame: pd.DataFrame) -> pd.Series:
    spread = frame.groupby("local_day")["target"].agg(lambda s: s.max() - s.min())
    threshold = float(spread.quantile(VOLATILE_QUANTILE)) if len(spread) else np.inf
    volatile_days = set(spread[spread >= threshold].index)
    return pd.Series(
        np.where(
            frame["target"] < 0,
            "negative prices",
            np.where(frame["local_day"].isin(volatile_days), "volatile days", "normal"),
        ),
        index=frame.index,
    )


def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()
