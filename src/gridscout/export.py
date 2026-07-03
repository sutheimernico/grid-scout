"""Export pipeline artifacts as compact JSON files for the static dashboard.

The site is fully static: these JSONs are its only data source. Keep them
small (the dashboard loads them on first paint) and stable in shape — the
frontend types mirror this module.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from gridscout.smard.filters import SERIES, Kind

GENERATION_ORDER = [
    # stack order for the mix chart: baseload-ish bottom, volatile top
    "gen_biomass",
    "gen_hydro",
    "gen_lignite",
    "gen_hard_coal",
    "gen_gas",
    "gen_other_conventional",
    "gen_pumped_storage",
    "gen_other_renewable",
    "gen_wind_offshore",
    "gen_wind_onshore",
    "gen_solar",
]
RENEWABLE = {
    "gen_biomass",
    "gen_hydro",
    "gen_other_renewable",
    "gen_wind_offshore",
    "gen_wind_onshore",
    "gen_solar",
}


def _read(data_dir: Path, name: str) -> pd.Series:
    df = pd.read_parquet(data_dir / f"{name}.parquet")
    idx = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    return pd.Series(df["value"].to_numpy(), index=idx, name=name)


def export_market(data_dir: Path, days: int = 14) -> dict:
    """Recent price/load/generation for the market view + headline KPIs."""
    price = _read(data_dir, "price_day_ahead")
    load = _read(data_dir, "load")
    cutoff = price.index.max() - pd.Timedelta(days=days)

    gen = {}
    for name in GENERATION_ORDER:
        if (data_dir / f"{name}.parquet").exists():
            gen[name] = _read(data_dir, name)
    gen_frame = pd.DataFrame(gen)

    recent_price = price[price.index > cutoff]
    recent_load = load[load.index > cutoff]
    recent_gen = gen_frame[gen_frame.index > cutoff]

    year_start = pd.Timestamp(datetime(price.index.max().year, 1, 1, tzinfo=UTC))
    year_prices = price[price.index >= year_start].dropna()
    last24_gen = gen_frame.dropna(how="all").tail(24)
    renewables_share = float(
        last24_gen[[c for c in last24_gen if c in RENEWABLE]].sum().sum()
        / max(last24_gen.sum().sum(), 1e-9)
    )

    return {
        "kpis": {
            "latest_price_eur_mwh": _round(price.dropna().iloc[-1]),
            "latest_price_at": price.dropna().index[-1].isoformat(),
            "negative_price_hours_ytd": int((year_prices < 0).sum()),
            "renewables_share_last_24h": round(renewables_share, 3),
        },
        "hourly": {
            "timestamps": [t.isoformat() for t in recent_price.index],
            "price": _values(recent_price),
            "load": _values(recent_load.reindex(recent_price.index)),
            "generation": {
                name: _values(recent_gen[name].reindex(recent_price.index))
                for name in recent_gen.columns
            },
        },
        "generation_labels": {
            name: SERIES[name].label.removeprefix("Generation: ")
            for name in GENERATION_ORDER
            if name in SERIES
        },
        "renewable_keys": sorted(RENEWABLE),
    }


def export_forecast(reports_dir: Path, days: int = 28) -> dict:
    """Eval metrics + the last weeks of walk-forward predictions vs reality."""
    eval_report = json.loads((reports_dir / "forecast_eval.json").read_text())
    predictions = pd.read_parquet(reports_dir / "predictions.parquet")
    predictions = predictions.sort_index()
    keep_days = sorted(predictions["local_day"].unique())[-days:]
    tail = predictions[predictions["local_day"].isin(keep_days)]
    return {
        "eval": eval_report,
        "recent": {
            "timestamps": [t.isoformat() for t in tail.index],
            "actual": _values(tail["target"]),
            "predicted": _values(tail["pred_point"]),
            "q10": _values(tail["pred_q10"]),
            "q90": _values(tail["pred_q90"]),
        },
    }


def export_battery(reports_dir: Path) -> dict:
    summary = json.loads((reports_dir / "battery_backtest.json").read_text())
    daily = pd.read_parquet(reports_dir / "battery_daily.parquet")
    daily["cum_perfect"] = daily["perfect"].cumsum()
    daily["cum_model"] = daily["model"].cumsum()
    daily["cum_naive"] = daily["naive"].cumsum()
    return {
        "summary": summary,
        "daily": {
            "days": daily["local_day"].astype(str).tolist(),
            "cumulative_perfect": _values(daily["cum_perfect"]),
            "cumulative_model": _values(daily["cum_model"]),
            "cumulative_naive": _values(daily["cum_naive"]),
        },
    }


def export_health(data_dir: Path) -> dict:
    """Freshness per series — the dashboard's pipeline-health panel."""
    series = {}
    for name, spec in SERIES.items():
        path = data_dir / f"{name}.parquet"
        if not path.exists():
            series[name] = {"status": "missing"}
            continue
        s = _read(data_dir, name).dropna()
        age_hours = (datetime.now(UTC) - s.index.max()).total_seconds() / 3600
        stale_after = 48 if spec.kind in (Kind.PRICE, Kind.FORECAST) else 96
        series[name] = {
            "status": "stale" if age_hours > stale_after else "ok",
            "last_value_at": s.index.max().isoformat(),
            "age_hours": round(age_hours, 1),
            "rows": int(len(s)),
        }
    return {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "series": series}


def export_site_data(data_dir: Path, reports_dir: Path, out_dir: Path) -> list[str]:
    """Write all artifacts; missing upstream reports are skipped, not fatal —
    the dashboard renders what exists and marks the rest as pending."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    exports = {
        "market.json": lambda: export_market(data_dir),
        "forecast.json": lambda: export_forecast(reports_dir),
        "battery.json": lambda: export_battery(reports_dir),
        "health.json": lambda: export_health(data_dir),
    }
    for filename, builder in exports.items():
        try:
            payload = builder()
        except FileNotFoundError:
            continue
        (out_dir / filename).write_text(json.dumps(payload, allow_nan=False) + "\n")
        written.append(filename)
    return written


def _values(series: pd.Series) -> list[float | None]:
    return [None if pd.isna(v) else round(float(v), 2) for v in series]


def _round(value: float) -> float:
    return round(float(value), 2)
