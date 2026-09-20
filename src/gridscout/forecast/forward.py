"""Forward test: one pre-auction forecast per delivery day, scored against reality.

Why this exists: every headline number on the site comes from a walk-forward
*backtest*, and a backtest can be re-run until it looks good. A ledger of
predictions written down before the outcome existed cannot.

The honesty contract, and the one place it bites:

- The German day-ahead auction closes 12:00 CET on D-1. A prediction for day D
  only counts if it was recorded before that.
- SMARD republishes the TSOs' generation forecast **for** day D only in the
  evening of D-1. Measured from this repo's own 3-hourly commit history
  (2026-09-13..20): at 12:10 UTC the forecast series still ends with D-1, and it
  only grows to cover D between roughly 17:00 and 21:00 UTC — after the auction,
  and after SMARD has published day D's cleared prices (those appear ~11:55 to
  14:10 UTC). Those forecast values are therefore not available to a SMARD-only
  pipeline at decision time, whatever the ENTSO-E transparency rules allow a
  trader with TSO feeds to see.
- So the live forecast runs on the reduced `PRE_AUCTION` feature set: calendar,
  price lags, load lags, and the generation-forecast series lagged by whole
  days. Nothing dated on the delivery day enters it. The backtest keeps the
  richer `FULL` set and is labelled accordingly; expect the live model to be
  weaker, and expect that gap to be the interesting number.

Every record stores what it takes to check it later: the information cutoff, the
feature set, a model fingerprint, and both baselines computed from the same
information at the same moment.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from gridscout.forecast.features import (
    PRE_AUCTION,
    TZ,
    FeatureSet,
    build_matrix,
    feature_columns,
    load_series_frame,
)
from gridscout.forecast.metrics import mae
from gridscout.forecast.models import LightGBMPrice

logger = logging.getLogger(__name__)

BERLIN = ZoneInfo(TZ)
LEDGER_FILENAME = "forward_ledger.parquet"
MIN_TRAIN_ROWS = 24 * 90

LEDGER_SCHEMA = pa.schema(
    [
        ("target_date", pa.string()),
        ("generated_at_utc", pa.string()),
        ("information_cutoff_utc", pa.string()),
        ("feature_set", pa.string()),
        ("model_version", pa.string()),
        ("train_days", pa.int32()),
        ("train_rows", pa.int32()),
        ("timestamps_utc", pa.list_(pa.string())),
        ("hours_local", pa.list_(pa.int16())),
        ("pred_model", pa.list_(pa.float64())),
        ("pred_naive", pa.list_(pa.float64())),
        ("pred_snaive7", pa.list_(pa.float64())),
        ("scored_at_utc", pa.string()),
        ("actual", pa.list_(pa.float64())),
        ("mae_model", pa.float64()),
        ("mae_naive", pa.float64()),
        ("mae_snaive7", pa.float64()),
        ("n_hours_scored", pa.int32()),
    ]
)


class NotForecastable(Exception):
    """The delivery day cannot be forecast honestly right now (and why)."""


@dataclass(frozen=True)
class ForwardConfig:
    train_days: int = 540
    n_estimators: int = 400
    seed: int = 42
    features: FeatureSet = PRE_AUCTION


def ledger_path(reports_dir: Path) -> Path:
    return reports_dir / LEDGER_FILENAME


def next_delivery_day(now: datetime | None = None) -> date:
    """Tomorrow, in German market time."""
    now = now or datetime.now(UTC)
    return (now.astimezone(BERLIN) + timedelta(days=1)).date()


def day_start_utc(day: date) -> pd.Timestamp:
    """00:00 Europe/Berlin of `day`, as a UTC timestamp."""
    return pd.Timestamp(day, tz=TZ).tz_convert("UTC")


def day_index_utc(day: date) -> pd.DatetimeIndex:
    """Every hour of a German calendar day, in UTC — 23, 24 or 25 of them."""
    start = pd.Timestamp(day, tz=TZ)
    end = pd.Timestamp(day + timedelta(days=1), tz=TZ)
    return pd.date_range(start, end, freq="h", inclusive="left").tz_convert("UTC")


def extend_to_delivery_day(raw: pd.DataFrame, day: date) -> pd.DataFrame:
    """Give the frame empty rows for the delivery day.

    The feature matrix is indexed by the raw frame, and under the pre-auction
    feature set *no* input series is dated on the delivery day — so without this
    the day has no rows to predict for.
    """
    return raw.reindex(raw.index.union(day_index_utc(day)))


def assert_no_target_day_leakage(raw: pd.DataFrame, target_day: date, features: FeatureSet) -> None:
    """Perturbation guard: nothing dated on or after the delivery day may move a
    delivery-day feature. Runs before every live forecast, not only in tests."""
    cutoff = day_start_utc(target_day)
    poisoned = raw.copy()
    poisoned.loc[poisoned.index >= cutoff, :] = 9_999_999.0

    clean_matrix = build_matrix(raw, require_target=False, features=features)
    dirty_matrix = build_matrix(poisoned, require_target=False, features=features)
    cols = feature_columns(clean_matrix)
    clean = clean_matrix[clean_matrix["local_day"] == target_day][cols]
    # reindex, not a plain filter: poisoning can only ADD rows (it fills gaps),
    # and a shape difference would mask the comparison we actually care about.
    dirty = dirty_matrix.reindex(clean.index)[cols]
    if not clean.equals(dirty):
        moved = [c for c in cols if not clean[c].equals(dirty[c])]
        raise NotForecastable(f"leakage guard tripped: delivery-day features moved: {moved}")


def model_version(config: ForwardConfig, columns: list[str]) -> str:
    """Short fingerprint so a later reader can tell which model wrote a record."""
    payload = json.dumps(
        {
            "features": config.features.name,
            "columns": sorted(columns),
            "n_estimators": config.n_estimators,
            "train_days": config.train_days,
            "seed": config.seed,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def make_prediction(data_dir: Path, target_day: date, config: ForwardConfig | None = None) -> dict:
    """Train on everything published before `target_day` and predict its prices.

    Raises NotForecastable when the delivery day's prices are already known (then
    it would be hindsight, not a forecast) or when its features are incomplete.
    """
    config = config or ForwardConfig()
    features = config.features
    raw = extend_to_delivery_day(load_series_frame(data_dir, features.raw_series), target_day)
    cutoff = day_start_utc(target_day)

    known = raw.loc[raw.index >= cutoff, features.target].dropna()
    if not known.empty:
        raise NotForecastable(
            f"day-ahead prices for {target_day} are already published "
            f"({len(known)} hours) — recording a forecast now would be hindsight"
        )

    assert_no_target_day_leakage(raw, target_day, features)

    matrix = build_matrix(raw, require_target=False, features=features)
    day_rows = matrix[matrix["local_day"] == target_day]
    if day_rows.empty:
        raise NotForecastable(
            f"no complete feature rows for {target_day} yet — SMARD has not published "
            "everything the pre-auction feature set needs"
        )

    train = matrix[
        (matrix["local_day"] < target_day)
        & (matrix["local_day"] >= target_day - timedelta(days=config.train_days))
        & matrix["target"].notna()
    ]
    if len(train) < MIN_TRAIN_ROWS:
        raise NotForecastable(
            f"only {len(train)} training rows available, need >= {MIN_TRAIN_ROWS}"
        )

    cols = feature_columns(matrix)
    model = LightGBMPrice(n_estimators=config.n_estimators, seed=config.seed)
    model.fit(train[cols], train["target"])
    predictions = np.asarray(model.predict(day_rows[cols]))

    return {
        "target_date": target_day.isoformat(),
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "information_cutoff_utc": cutoff.isoformat(),
        "feature_set": features.name,
        "model_version": model_version(config, cols),
        "train_days": int(config.train_days),
        "train_rows": int(len(train)),
        # UTC timestamps, not local hours: on the October DST day a local hour
        # occurs twice, and scoring by hour would silently use one price twice.
        "timestamps_utc": [ts.isoformat() for ts in day_rows.index],
        "hours_local": [int(h) for h in day_rows["hour_local"]],
        "pred_model": [round(float(v), 2) for v in predictions],
        "pred_naive": [round(float(v), 2) for v in day_rows["price_lag_1d"]],
        "pred_snaive7": [round(float(v), 2) for v in day_rows["price_lag_7d"]],
        "scored_at_utc": None,
        "actual": None,
        "mae_model": None,
        "mae_naive": None,
        "mae_snaive7": None,
        "n_hours_scored": None,
    }


def read_ledger(reports_dir: Path) -> list[dict]:
    path = ledger_path(reports_dir)
    if not path.exists():
        return []
    return pq.read_table(path).to_pylist()


def write_ledger(reports_dir: Path, records: list[dict]) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda r: r["target_date"])
    path = ledger_path(reports_dir)
    pq.write_table(pa.Table.from_pylist(ordered, schema=LEDGER_SCHEMA), path)
    return path


def append_record(reports_dir: Path, record: dict) -> bool:
    """Insert or replace the pending record for its delivery day.

    A scored record is history and is never overwritten — re-running the daily
    job must not be able to improve yesterday's prediction after the fact.
    """
    records = read_ledger(reports_dir)
    by_day = {r["target_date"]: r for r in records}
    existing = by_day.get(record["target_date"])
    if existing is not None and existing.get("scored_at_utc"):
        logger.info("%s is already scored — keeping the original record", record["target_date"])
        return False
    by_day[record["target_date"]] = record
    write_ledger(reports_dir, list(by_day.values()))
    return True


def score_ledger(data_dir: Path, reports_dir: Path) -> list[dict]:
    """Score every pending record whose delivery day has cleared.

    Returns the records scored in this pass. Records whose day is only partly
    published are left pending — a half-scored day would quietly bias the MAE.
    """
    records = read_ledger(reports_dir)
    if not records:
        return []
    prices = _hourly_prices(data_dir)
    scored_now = []
    for record in records:
        if record.get("scored_at_utc"):
            continue
        stamps = list(record["timestamps_utc"])
        if any(ts not in prices for ts in stamps):
            continue
        truth = np.array([prices[ts] for ts in stamps], dtype=float)
        record["actual"] = [round(float(v), 2) for v in truth]
        for key in ("model", "naive", "snaive7"):
            record[f"mae_{key}"] = round(
                mae(truth, np.array(record[f"pred_{key}"], dtype=float)), 4
            )
        record["n_hours_scored"] = len(stamps)
        record["scored_at_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
        scored_now.append(record)
    if scored_now:
        write_ledger(reports_dir, records)
    return scored_now


def summarize_ledger(records: list[dict]) -> dict:
    """Track record for the site: cumulative and last-7-day skill vs the baselines."""
    scored = sorted((r for r in records if r.get("scored_at_utc")), key=lambda r: r["target_date"])
    return {
        "n_records": len(records),
        "n_scored": len(scored),
        "n_pending": len(records) - len(scored),
        "first_target_date": min((r["target_date"] for r in records), default=None),
        "last_target_date": max((r["target_date"] for r in records), default=None),
        "feature_set": records[-1]["feature_set"] if records else None,
        "cumulative": window_stats(scored),
        "last_7_days": window_stats(scored[-7:]),
    }


def window_stats(scored: list[dict]) -> dict | None:
    """Hour-weighted error over a set of scored days (None when there are none)."""
    if not scored:
        return None
    hours = sum(r["n_hours_scored"] for r in scored)
    weighted = {
        key: sum(r[f"mae_{key}"] * r["n_hours_scored"] for r in scored) / hours
        for key in ("model", "naive", "snaive7")
    }
    return {
        "n_days": len(scored),
        "n_hours": hours,
        "mae_model": round(weighted["model"], 2),
        "mae_naive": round(weighted["naive"], 2),
        "mae_snaive7": round(weighted["snaive7"], 2),
        "skill_vs_naive_pct": (
            round(100 * (1 - weighted["model"] / weighted["naive"]), 1)
            if weighted["naive"]
            else None
        ),
        "days_model_beat_naive": sum(1 for r in scored if r["mae_model"] < r["mae_naive"]),
    }


def _hourly_prices(data_dir: Path) -> dict[str, float]:
    """UTC ISO timestamp -> cleared day-ahead price."""
    df = pd.read_parquet(data_dir / "price_day_ahead.parquet")
    idx = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    return {
        ts.isoformat(): float(value)
        for ts, value in zip(idx, df["value"], strict=True)
        if not pd.isna(value)
    }
