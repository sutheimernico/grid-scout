"""Walk-forward evaluation of all models + honest report generation."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from gridscout.forecast.features import (
    DAY_AHEAD_SERIES,
    REALIZED_LAG_DAYS,
    TARGET,
    build_matrix,
    load_series_frame,
    local_days,
)
from gridscout.forecast.metrics import coverage, pinball, summarize
from gridscout.forecast.models import LightGBMPrice, NaiveYesterday, SeasonalNaiveWeek
from gridscout.forecast.walkforward import make_folds, run_walkforward

RAW_SERIES = [TARGET, *DAY_AHEAD_SERIES, *REALIZED_LAG_DAYS]


@dataclass
class EvalConfig:
    eval_days: int = 365
    step_days: int = 7
    seed: int = 42


def evaluate(data_dir: Path, config: EvalConfig | None = None) -> tuple[dict, pd.DataFrame]:
    """Returns (report, predictions). Predictions carry every model's forecast
    per hour of the eval period — the battery backtest consumes them."""
    config = config or EvalConfig()
    raw = load_series_frame(data_dir, RAW_SERIES)
    matrix = build_matrix(raw)
    days = local_days(matrix)
    min_train = len(days) - config.eval_days
    if min_train < 365:
        raise ValueError(f"not enough history: {len(days)} days total, need eval + >=1y train")
    folds = make_folds(days, min_train_days=min_train, step_days=config.step_days)

    point_models = [NaiveYesterday(), SeasonalNaiveWeek(), LightGBMPrice(seed=config.seed)]
    results = {m.name: run_walkforward(matrix, m, folds) for m in point_models}
    q10 = run_walkforward(matrix, LightGBMPrice(quantile=0.1, seed=config.seed), folds)
    q90 = run_walkforward(matrix, LightGBMPrice(quantile=0.9, seed=config.seed), folds)

    predictions = results["lgbm_point"][["local_day", "hour_local", "target"]].copy()
    predictions["pred_point"] = results["lgbm_point"]["prediction"]
    predictions["pred_naive"] = results["naive_yesterday"]["prediction"]
    predictions["pred_snaive7"] = results["seasonal_naive_7d"]["prediction"]
    predictions["pred_q10"] = q10["prediction"]
    predictions["pred_q90"] = q90["prediction"]

    report: dict = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "eval_period": {
            "start": str(min(results["lgbm_point"]["local_day"])),
            "end": str(max(results["lgbm_point"]["local_day"])),
            "n_days": int(results["lgbm_point"]["local_day"].nunique()),
            "refit_every_days": config.step_days,
        },
        "models": {},
    }
    for name, frame in results.items():
        report["models"][name] = summarize(
            frame["target"].to_numpy(),
            frame["prediction"].to_numpy(),
            frame["hour_local"].to_numpy(),
        )

    y = q10["target"].to_numpy()
    report["quantiles"] = {
        "pinball_q10": pinball(y, q10["prediction"].to_numpy(), 0.1),
        "pinball_q90": pinball(y, q90["prediction"].to_numpy(), 0.9),
        "coverage_p10_p90": coverage(y, q10["prediction"].to_numpy(), q90["prediction"].to_numpy()),
        "target_coverage": 0.8,
    }

    lgbm = report["models"]["lgbm_point"]["mae"]
    naive = report["models"]["naive_yesterday"]["mae"]
    snaive = report["models"]["seasonal_naive_7d"]["mae"]
    report["skill"] = {
        "lgbm_vs_naive_pct": round(100 * (1 - lgbm / naive), 1),
        "lgbm_vs_seasonal_naive_pct": round(100 * (1 - lgbm / snaive), 1),
    }
    report["finding"] = _verdict(report)
    return report, predictions


def _verdict(report: dict) -> str:
    """One honest sentence — written by rule, not by optimism."""
    skill = report["skill"]["lgbm_vs_naive_pct"]
    cov = report["quantiles"]["coverage_p10_p90"]
    mae = report["models"]["lgbm_point"]["mae"]
    if skill <= 0:
        head = (
            f"NEGATIVE RESULT: LightGBM (MAE {mae:.2f} EUR/MWh) does not beat the "
            f"naive yesterday-price baseline ({skill:+.1f}%)."
        )
    elif skill < 5:
        head = (
            f"MARGINAL: LightGBM improves on the naive baseline by only {skill:+.1f}% "
            f"(MAE {mae:.2f} EUR/MWh)."
        )
    else:
        head = (
            f"LightGBM beats the naive baseline by {skill:+.1f}% "
            f"(MAE {mae:.2f} EUR/MWh)."
        )
    return head + (
        f" The p10-p90 band covers {cov:.0%} of outcomes (target 80%)."
        " Metrics are walk-forward, leakage-guarded, over the full eval period"
        " including nights and weekends."
    )


def write_report(report: dict, predictions: pd.DataFrame, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / "forecast_eval.json"
    path.write_text(json.dumps(report, indent=2, default=_json_default) + "\n")
    predictions.assign(local_day=predictions["local_day"].astype(str)).to_parquet(
        reports_dir / "predictions.parquet"
    )
    return path


def _json_default(obj):
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    raise TypeError(f"not JSON serializable: {type(obj)}")
