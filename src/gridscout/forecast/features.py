"""Feature matrix for the day-ahead price forecast.

Availability contract — the model predicts all 24 hourly prices of day D at
D-1 ~12:00 Europe/Berlin, i.e. before EPEX day-ahead gate closure. At that
moment the following is known and nothing else:

- day-ahead prices through the END of D-1 (auctioned on D-2), so price lags
  of >= 1 day are safe;
- realized load/generation only through D-2 (D-1 is still incomplete at noon),
  so realization lags must be >= 2 days;
- SMARD's published generation forecasts FOR day D (wind/solar/total). Caveat,
  documented honestly: SMARD stores the latest forecast revision, not the
  auction-time snapshot — treated as day-ahead information here.

Lags are exact multiples of 24 absolute hours. Around DST switches this
misaligns local hour by one for a single day — accepted simplification.

The leakage test in tests/test_features.py enforces this contract by
perturbation, not by trust.
"""

from datetime import date
from pathlib import Path

import holidays
import pandas as pd

TZ = "Europe/Berlin"
TARGET = "price_day_ahead"

# Series whose value AT the target hour is day-ahead information.
DAY_AHEAD_SERIES = [
    "forecast_solar",
    "forecast_wind_onshore",
    "forecast_wind_offshore",
    "forecast_generation_total",
]
PRICE_LAG_DAYS = [1, 2, 7]
REALIZED_LAG_DAYS = {"load": [2, 7]}

CALENDAR_FEATURES = ["hour_local", "day_of_week", "month", "is_weekend", "is_holiday"]


def load_series_frame(data_dir: Path, names: list[str]) -> pd.DataFrame:
    """Wide hourly frame, UTC DatetimeIndex, one column per series."""
    columns = {}
    for name in names:
        df = pd.read_parquet(data_dir / f"{name}.parquet")
        idx = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
        columns[name] = pd.Series(df["value"].to_numpy(), index=idx)
    return pd.DataFrame(columns).sort_index()


def build_matrix(raw: pd.DataFrame, require_target: bool = True) -> pd.DataFrame:
    """Feature matrix + `target` column, indexed by UTC hour.

    raw: wide frame from load_series_frame containing TARGET, DAY_AHEAD_SERIES
    and the keys of REALIZED_LAG_DAYS. Rows with missing features are dropped
    (lags eat the first 7 days). With require_target=False, rows whose target
    is still unknown are kept — that is the inference case: tomorrow's
    forecasts exist, tomorrow's price does not.
    """
    out = pd.DataFrame(index=raw.index)
    out["target"] = raw[TARGET]

    for name in DAY_AHEAD_SERIES:
        out[name] = raw[name]
    for lag in PRICE_LAG_DAYS:
        out[f"price_lag_{lag}d"] = raw[TARGET].shift(freq=pd.Timedelta(days=lag))
    for name, lags in REALIZED_LAG_DAYS.items():
        for lag in lags:
            out[f"{name}_lag_{lag}d"] = raw[name].shift(freq=pd.Timedelta(days=lag))

    local = out.index.tz_convert(TZ)
    de_holidays = holidays.country_holidays("DE", years=sorted({d.year for d in local.date}))
    out["hour_local"] = local.hour
    out["day_of_week"] = local.dayofweek
    out["month"] = local.month
    out["is_weekend"] = (local.dayofweek >= 5).astype(int)
    out["is_holiday"] = pd.Series(local.date, index=out.index).map(
        lambda d: int(d in de_holidays)
    )
    out["local_day"] = pd.Series(local.date, index=out.index)

    drop_cols = ["local_day"] if require_target else ["local_day", "target"]
    feature_rows = out.drop(columns=drop_cols).notna().all(axis=1)
    return out[feature_rows]


def feature_columns(matrix: pd.DataFrame) -> list[str]:
    return [c for c in matrix.columns if c not in ("target", "local_day")]


def local_days(matrix: pd.DataFrame) -> list[date]:
    return sorted(matrix["local_day"].unique())
