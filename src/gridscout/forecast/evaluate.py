"""Walk-forward evaluation of all models + honest report generation."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from gridscout.forecast.conformal import conformalize
from gridscout.forecast.features import (
    FULL,
    PRE_AUCTION,
    build_matrix,
    load_series_frame,
    local_days,
)
from gridscout.forecast.metrics import coverage, pinball, summarize
from gridscout.forecast.models import (
    LightGBMPrice,
    NaiveYesterday,
    RidgePerHour,
    SeasonalNaiveWeek,
)
from gridscout.forecast.walkforward import make_folds, run_walkforward

RAW_SERIES = list(dict.fromkeys([*FULL.raw_series, *PRE_AUCTION.raw_series]))


@dataclass
class EvalConfig:
    eval_days: int = 365
    step_days: int = 7
    seed: int = 42
    target_coverage: float = 0.8


def evaluate(data_dir: Path, config: EvalConfig | None = None) -> tuple[dict, pd.DataFrame]:
    """Returns (report, predictions). Predictions carry every model's forecast
    per hour of the eval period — the battery backtest consumes them."""
    config = config or EvalConfig()
    raw = load_series_frame(data_dir, RAW_SERIES)
    matrix = build_matrix(raw, features=FULL)
    days = local_days(matrix)
    min_train = len(days) - config.eval_days
    if min_train < 365:
        raise ValueError(f"not enough history: {len(days)} days total, need eval + >=1y train")
    folds = make_folds(days, min_train_days=min_train, step_days=config.step_days)

    point_models = [
        NaiveYesterday(),
        SeasonalNaiveWeek(),
        RidgePerHour(),
        LightGBMPrice(seed=config.seed),
    ]
    results = {m.name: run_walkforward(matrix, m, folds) for m in point_models}
    q10 = run_walkforward(matrix, LightGBMPrice(quantile=0.1, seed=config.seed), folds)
    q90 = run_walkforward(matrix, LightGBMPrice(quantile=0.9, seed=config.seed), folds)

    predictions = results["lgbm_point"][["local_day", "hour_local", "target"]].copy()
    predictions["pred_point"] = results["lgbm_point"]["prediction"]
    predictions["pred_naive"] = results["naive_yesterday"]["prediction"]
    predictions["pred_snaive7"] = results["seasonal_naive_7d"]["prediction"]
    predictions["pred_ridge"] = results["ridge_per_hour"]["prediction"]
    predictions["pred_q10"] = q10["prediction"]
    predictions["pred_q90"] = q90["prediction"]

    # Same models on the strictly pre-auction inputs (nothing dated on the
    # delivery day). Scored on exactly the hours the gate-closure run is scored on.
    # Known gap: a delivery day whose lagged inputs are missing has no pre-auction
    # forecast (rows with missing features are dropped, nothing is imputed). In the
    # committed run that is 2026-10-25 (24 of 8,761 hours): SMARD's generation
    # forecast series have 24-hour holes (solar, onshore wind: 2026-10-24; total: 23-24
    # Oct), and the lag-1 features need it. It is a hole in the source, not the DST change of that day.
    pre_matrix = build_matrix(raw, features=PRE_AUCTION)
    pre_models = [LightGBMPrice(seed=config.seed), RidgePerHour()]
    pre_results = {m.name: run_walkforward(pre_matrix, m, folds) for m in pre_models}
    common = predictions.index.intersection(pre_results["lgbm_point"].index)
    predictions["pred_point_pre_auction"] = pre_results["lgbm_point"]["prediction"]
    predictions["pred_ridge_pre_auction"] = pre_results["ridge_per_hour"]["prediction"]
    calibrated = conformalize(predictions, alpha=1 - config.target_coverage)
    predictions["q_low_cal"] = calibrated["q_low_cal"]
    predictions["q_high_cal"] = calibrated["q_high_cal"]

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

    scored = calibrated.dropna(subset=["q_low_cal"])
    report["quantiles"]["conformal"] = {
        "method": "walk-forward split conformal (CQR), calibrated on all earlier weeks",
        "coverage_p10_p90": coverage(
            scored["target"].to_numpy(),
            scored["q_low_cal"].to_numpy(),
            scored["q_high_cal"].to_numpy(),
        ),
        "raw_coverage_same_hours": coverage(
            scored["target"].to_numpy(),
            scored["pred_q10"].to_numpy(),
            scored["pred_q90"].to_numpy(),
        ),
        "mean_width_raw": float((scored["pred_q90"] - scored["pred_q10"]).mean()),
        "mean_width_calibrated": float((scored["q_high_cal"] - scored["q_low_cal"]).mean()),
        "n_hours": int(len(scored)),
    }

    on_common = {
        "naive_yesterday": results["naive_yesterday"].loc[common],
        "seasonal_naive_7d": results["seasonal_naive_7d"].loc[common],
        "ridge_gate_closure": results["ridge_per_hour"].loc[common],
        "lgbm_gate_closure": results["lgbm_point"].loc[common],
        "ridge_pre_auction": pre_results["ridge_per_hour"].loc[common],
        "lgbm_pre_auction": pre_results["lgbm_point"].loc[common],
    }
    report["pre_auction"] = {
        "description": (
            "Same walk-forward, but with the strictly pre-auction feature set: no input is "
            "dated on the delivery day (SMARD publishes its generation forecast for day D "
            "only 17-21 UTC on D-1, after the 12:00 auction). *_gate_closure models use the "
            "TSO forecast for day D, as a trader with TSO feeds would have it at 12:00."
        ),
        "n": int(len(common)),
        "models": {
            name: summarize(
                frame["target"].to_numpy(),
                frame["prediction"].to_numpy(),
                frame["hour_local"].to_numpy(),
            )
            for name, frame in on_common.items()
        },
    }
    pre = report["pre_auction"]["models"]
    report["pre_auction"]["skill_vs_naive_pct"] = round(
        100 * (1 - pre["lgbm_pre_auction"]["mae"] / pre["naive_yesterday"]["mae"]), 1
    )

    lgbm = report["models"]["lgbm_point"]["mae"]
    naive = report["models"]["naive_yesterday"]["mae"]
    snaive = report["models"]["seasonal_naive_7d"]["mae"]
    report["skill"] = {
        "lgbm_vs_naive_pct": round(100 * (1 - lgbm / naive), 1),
        "lgbm_vs_seasonal_naive_pct": round(100 * (1 - lgbm / snaive), 1),
        "lgbm_vs_ridge_pct": round(100 * (1 - lgbm / report["models"]["ridge_per_hour"]["mae"]), 1),
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
        head = f"LightGBM beats the naive baseline by {skill:+.1f}% (MAE {mae:.2f} EUR/MWh)."
    pre = report["pre_auction"]["models"]["lgbm_pre_auction"]["mae"]
    ridge = report["models"]["ridge_per_hour"]["mae"]
    cal = report["quantiles"]["conformal"]["coverage_p10_p90"]
    return head + (
        f" A per-hour ridge (LEAR-style) baseline scores MAE {ridge:.2f}."
        " Assumes the TSOs' day-ahead generation forecast is known at gate closure;"
        f" on strictly pre-auction SMARD inputs the model scores MAE {pre:.2f}."
        f" The raw p10-p90 band covers {cov:.0%} of outcomes (target 80%);"
        f" conformal calibration brings it to {cal:.0%}."
        " Metrics are walk-forward over the full eval period including nights and weekends."
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
