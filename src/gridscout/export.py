"""Export pipeline artifacts as compact JSON files for the static dashboard.

The site is fully static: these JSONs are its only data source. Keep them
small (the dashboard loads them on first paint) and stable in shape — the
frontend types mirror this module.
"""

import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from gridscout.analysis import captions
from gridscout.forecast.segments import segment_errors
from gridscout.smard.filters import SERIES, Kind

TZ = "Europe/Berlin"


def _round_long_floats(text: str) -> str:
    """Display hygiene: '15.253157140946763' -> '15.25' inside gold strings."""
    return re.sub(r"\d+\.\d{4,}", lambda m: f"{float(m.group()):.2f}", text)


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
        "explanation": _explain_latest_day(price, load, gen_frame),
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


def _explain_latest_day(price: pd.Series, load: pd.Series, gen: pd.DataFrame) -> dict | None:
    """Rule-written caption for the last fully covered local day, or None.

    None rather than a half-day caption: a sentence about "the cheapest hour"
    built from six hours of data would be wrong in a way nobody could see.
    """
    wind_cols = [c for c in ("gen_wind_onshore", "gen_wind_offshore") if c in gen]
    if "gen_solar" not in gen or not wind_cols:
        return None
    frame = captions.align(price, load, gen["gen_solar"], gen[wind_cols].sum(axis=1))
    if frame.empty:
        return None
    days = pd.Series(frame.index.tz_convert(TZ).date, index=frame.index)
    counts = days.value_counts()
    # 23 not 24: the March DST day is a full day with 23 hours
    complete = sorted(day for day, n in counts.items() if n >= 23)
    if not complete:
        return None
    day = complete[-1]
    return {"day": day.isoformat(), **captions.describe(frame[days == day])}


def export_forecast(reports_dir: Path, days: int = 28) -> dict:
    """Eval metrics + the last weeks of walk-forward predictions vs reality."""
    eval_report = json.loads((reports_dir / "forecast_eval.json").read_text())
    predictions = pd.read_parquet(reports_dir / "predictions.parquet")
    predictions = predictions.sort_index()
    keep_days = sorted(predictions["local_day"].unique())[-days:]
    tail = predictions[predictions["local_day"].isin(keep_days)]
    return {
        "eval": eval_report,
        "segments": segment_errors(predictions),
        "recent": {
            "timestamps": [t.isoformat() for t in tail.index],
            "actual": _values(tail["target"]),
            "predicted": _values(tail["pred_point"]),
            # strictly pre-auction model; null for the one day it has no features for
            "predicted_pre_auction": (
                _values(tail["pred_point_pre_auction"])
                if "pred_point_pre_auction" in tail
                else None
            ),
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
    out = {
        "summary": summary,
        "daily": {
            "days": daily["local_day"].astype(str).tolist(),
            "cumulative_perfect": _values(daily["cum_perfect"]),
            "cumulative_model": _values(daily["cum_model"]),
            "cumulative_naive": _values(daily["cum_naive"]),
        },
    }
    # Optional: the sweep is written by the weekly full eval only, so the battery
    # section must not disappear in the window before its first run.
    sensitivity = reports_dir / "battery_sensitivity.json"
    if sensitivity.exists():
        out["sensitivity"] = json.loads(sensitivity.read_text())
    return out


def export_agent(reports_dir: Path, examples_per_type: int = 2) -> dict:
    """Agent eval summary + curated example transcripts for the dashboard."""
    report = json.loads((reports_dir / "agent_eval.json").read_text())
    examples: list[dict] = []
    seen: dict[str, int] = {}
    # prefer one pass and one fail per type so the page shows real behavior,
    # not a highlight reel
    for want_pass in (True, False):
        for r in report["results"]:
            key = f"{r['type']}-{want_pass}"
            if r["passed"] is want_pass and seen.get(key, 0) < examples_per_type // 2 + 1:
                seen[key] = seen.get(key, 0) + 1
                examples.append(
                    {
                        "type": r["type"],
                        "question": r["question"],
                        "answer": r["answer"],
                        "gold": _round_long_floats(r["gold"]),
                        "passed": r["passed"],
                        "tools_used": [c["tool"] for c in r["tool_calls"]],
                    }
                )
    out = {
        "model": report["model"],
        "generated_utc": report.get("generated_utc"),
        "n": report["n"],
        "pass_rate": report["pass_rate"],
        "regraded": sum(bool(r.get("regraded_fail")) for r in report["results"]),
        "by_type": report["by_type"],
        "grading": report["grading"],
        "examples": examples,
    }
    holdout_path = reports_dir / "agent_eval_holdout.json"
    if holdout_path.exists():
        holdout = json.loads(holdout_path.read_text())
        out["holdout"] = {k: holdout[k] for k in ("n", "passed", "pass_rate", "by_type")}
    return out


@dataclass(frozen=True)
class ReportSpec:
    """Freshness contract for a derived report.

    `cadence_days=None` means nobody promises a schedule (the agent eval needs a
    local Ollama run), so its row is informational and never alarms.
    """

    label: str
    timestamp_key: str
    cadence_days: int | None = None
    warn_after_days: int = 8
    overdue_after_days: int = 15


# Written by the weekly full-eval run; the 3-hourly run only refreshes raw data.
REPORT_SPECS: dict[str, ReportSpec] = {
    "forecast_eval.json": ReportSpec("Forecast walk-forward eval", "generated_utc", cadence_days=7),
    "battery_backtest.json": ReportSpec("Battery backtest", "generated_utc", cadence_days=7),
    "battery_sensitivity.json": ReportSpec(
        "Battery sensitivity sweep", "generated_utc", cadence_days=7
    ),
    "agent_eval.json": ReportSpec("Agent eval (local Ollama)", "generated_utc"),
}


def export_report_health(reports_dir: Path) -> dict:
    """Freshness of the derived reports the dashboard quotes numbers from.

    Without this, a silently dead weekly eval would keep serving months-old
    forecast metrics under an all-green health panel — the raw series stay
    fresh, so nothing else would notice.
    """
    now = datetime.now(UTC)
    out = {}
    for filename, spec in REPORT_SPECS.items():
        entry: dict = {
            "label": spec.label,
            "cadence_days": spec.cadence_days,
        }
        path = reports_dir / filename
        if not path.exists():
            out[filename] = {**entry, "status": "missing"}
            continue
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            out[filename] = {**entry, "status": "unreadable"}
            continue
        stamp = payload.get(spec.timestamp_key)
        if not stamp:
            # File mtime is the checkout time in CI, so guessing would produce a
            # false green. An unknown age is reported as unknown.
            out[filename] = {**entry, "status": "unknown"}
            continue
        age_days = (now - datetime.fromisoformat(stamp)).total_seconds() / 86400
        if spec.cadence_days is None:
            status = "manual"
        elif age_days > spec.overdue_after_days:
            status = "overdue"
        elif age_days > spec.warn_after_days:
            status = "aging"
        else:
            status = "ok"
        out[filename] = {
            **entry,
            "status": status,
            "generated_at": stamp,
            "age_days": round(age_days, 1),
            "warn_after_days": spec.warn_after_days,
            "overdue_after_days": spec.overdue_after_days,
        }
    return out


LEDGER_DAYS_ON_SITE = 60

# The pipeline's own commit-back message. Counting these per day is the only
# self-recorded evidence of unattended operation that costs nothing to keep.
BOT_COMMIT_SUBJECT = "chore(pipeline): refresh data artifacts"
# Cron slots per day: 8 three-hourly runs + 2 pre-auction forecast slots.
SCHEDULED_RUNS_PER_DAY = 10


def _git_run_days(repo_root: Path) -> dict[str, int]:
    """UTC date -> number of pipeline commits, from git. {} if git cannot answer."""
    try:
        result = subprocess.run(
            ["git", "log", "--fixed-strings", f"--grep={BOT_COMMIT_SUBJECT}", "--format=%cI"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    stamps = [
        datetime.fromisoformat(line).astimezone(UTC).date().isoformat()
        for line in result.stdout.splitlines()
        if line.strip()
    ]
    return dict(Counter(stamps))


def export_uptime(repo_root: Path, previous: Path | None = None) -> dict:
    """Runs per day since the pipeline went live — the heartbeat, as a calendar.

    Two sources, merged by max(): git history (authoritative, but a shallow CI
    checkout only sees the newest commit) and the previously exported artifact
    (which the pipeline commits back, so it accumulates whatever git forgets).
    Days with no run stay in the series at zero — a gap that is hidden is a lie.
    """
    counts = _git_run_days(repo_root)
    if previous is not None and previous.exists():
        try:
            old_days = json.loads(previous.read_text()).get("days", [])
        except json.JSONDecodeError:
            old_days = []
        for entry in old_days:
            day, runs = entry["date"], int(entry["runs"])
            counts[day] = max(counts.get(day, 0), runs)
    if not counts:
        raise FileNotFoundError("no pipeline history to build an uptime calendar from")

    first = date.fromisoformat(min(counts))
    last = max(date.fromisoformat(max(counts)), datetime.now(UTC).date())
    days = []
    cursor = first
    while cursor <= last:
        days.append({"date": cursor.isoformat(), "runs": counts.get(cursor.isoformat(), 0)})
        cursor += timedelta(days=1)

    active = sorted(d["runs"] for d in days if d["runs"] > 0)
    # Colour reference is the median ACTIVE day, not the cron slot count: a run
    # that finds no new SMARD data publishes nothing and leaves no commit, and
    # GitHub delays and drops some scheduled runs (measured: 4-6 of 8 three-hourly
    # slots start per day, median ~1.7 h late). Scaling against the slot count
    # would paint a healthy pipeline as permanently pale.
    reference = active[len(active) // 2] if active else 1

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": (
            "one cell per UTC day, counting the pipeline's own commit-back commits — "
            "i.e. published refreshes, not attempted runs; a run that finds no new "
            "SMARD data commits nothing. Merged with the previously published "
            "calendar so a shallow CI clone cannot lose history."
        ),
        "scheduled_runs_per_day": SCHEDULED_RUNS_PER_DAY,
        "reference_runs_per_day": reference,
        "first_day": first.isoformat(),
        "days": days,
        "totals": {
            "days": len(days),
            "runs": sum(d["runs"] for d in days),
            "days_with_a_run": len(active),
            "days_with_zero_runs": len(days) - len(active),
            "longest_silent_streak_days": _longest_zero_streak(days),
            "median_runs_per_active_day": reference,
        },
    }


def _longest_zero_streak(days: list[dict]) -> int:
    longest = current = 0
    for day in days:
        current = current + 1 if day["runs"] == 0 else 0
        longest = max(longest, current)
    return longest


def export_forward_ledger(reports_dir: Path) -> dict:
    """The live track record: what was predicted before the auction, and how it did.

    Raises FileNotFoundError before the first daily run so the dashboard shows
    its pending state instead of an empty, authoritative-looking panel.
    """
    from gridscout.forecast.forward import ledger_path, read_ledger, summarize_ledger

    if not ledger_path(reports_dir).exists():
        raise FileNotFoundError(ledger_path(reports_dir))
    records = read_ledger(reports_dir)
    days = [
        {
            "target_date": r["target_date"],
            "generated_at_utc": r["generated_at_utc"],
            "scored": bool(r["scored_at_utc"]),
            "mae_model": r["mae_model"],
            "mae_naive": r["mae_naive"],
            "mae_snaive7": r["mae_snaive7"],
        }
        for r in sorted(records, key=lambda r: r["target_date"])[-LEDGER_DAYS_ON_SITE:]
    ]
    latest = max(records, key=lambda r: r["target_date"], default=None)
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "method": (
            "One forecast per delivery day, recorded before the 12:00 CET day-ahead "
            "auction closes, on a feature set that contains nothing dated on the "
            "delivery day. Scored against the cleared prices once they publish."
        ),
        "summary": summarize_ledger(records),
        "days": days,
        "latest": None
        if latest is None
        else {
            "target_date": latest["target_date"],
            "generated_at_utc": latest["generated_at_utc"],
            "scored": bool(latest["scored_at_utc"]),
            "hours_local": list(latest["hours_local"]),
            "pred_model": list(latest["pred_model"]),
            "pred_naive": list(latest["pred_naive"]),
            "actual": list(latest["actual"]) if latest["actual"] is not None else None,
        },
    }


def export_health(data_dir: Path, reports_dir: Path | None = None) -> dict:
    """Freshness per series — the dashboard's pipeline-health panel."""
    series = {}
    for name, spec in SERIES.items():
        path = data_dir / f"{name}.parquet"
        if not path.exists():
            series[name] = {"status": "missing", "label": spec.label}
            continue
        s = _read(data_dir, name).dropna()
        age_hours = (datetime.now(UTC) - s.index.max()).total_seconds() / 3600
        stale_after = 48 if spec.kind in (Kind.PRICE, Kind.FORECAST) else 96
        entry = {
            "status": "stale" if age_hours > stale_after else "ok",
            "label": spec.label,
            "last_value_at": s.index.max().isoformat(),
            "age_hours": round(age_hours, 1),
            "rows": int(len(s)),
        }
        if spec.discontinued:
            # A series SMARD no longer publishes can never be fresh again. Reporting
            # it as stale is a permanent false alarm that trains the reader to
            # ignore the panel — the one thing an alerting surface must not do.
            entry["status"] = "discontinued"
            entry["note"] = spec.discontinued
        series[name] = entry
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "series": series,
        "reports": export_report_health(reports_dir) if reports_dir is not None else {},
    }


def export_site_data(
    data_dir: Path, reports_dir: Path, out_dir: Path, repo_root: Path | None = None
) -> list[str]:
    """Write all artifacts; missing upstream reports are skipped, not fatal —
    the dashboard renders what exists and marks the rest as pending."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    exports = {
        "market.json": lambda: export_market(data_dir),
        "forecast.json": lambda: export_forecast(reports_dir),
        "battery.json": lambda: export_battery(reports_dir),
        "agent.json": lambda: export_agent(reports_dir),
        "forward_ledger.json": lambda: export_forward_ledger(reports_dir),
        "health.json": lambda: export_health(data_dir, reports_dir),
        "uptime.json": lambda: export_uptime(repo_root or Path.cwd(), out_dir / "uptime.json"),
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
