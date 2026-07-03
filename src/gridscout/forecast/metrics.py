"""Forecast error metrics, implemented directly (no sklearn dependency)."""

import numpy as np
import pandas as pd


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def pinball(y_true: np.ndarray, y_pred: np.ndarray, quantile: float) -> float:
    diff = y_true - y_pred
    return float(np.mean(np.maximum(quantile * diff, (quantile - 1) * diff)))


def coverage(y_true: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    """Fraction of observations inside [lower, upper]."""
    return float(np.mean((y_true >= lower) & (y_true <= upper)))


def summarize(y_true: np.ndarray, y_pred: np.ndarray, hours: np.ndarray) -> dict:
    """Overall + per-local-hour error summary."""
    frame = pd.DataFrame({"true": y_true, "pred": y_pred, "hour": hours})
    by_hour = {
        int(hour): mae(g["true"].to_numpy(), g["pred"].to_numpy())
        for hour, g in frame.groupby("hour")
    }
    return {
        "mae": mae(y_true, y_pred),
        "rmse": rmse(y_true, y_pred),
        "mae_by_hour": by_hour,
        "n": int(len(y_true)),
    }
