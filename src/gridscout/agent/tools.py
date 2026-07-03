"""Data-grounded tools — the single source both the MCP server and the local
agent loop expose. Every function returns plain JSON-serializable dicts and
raises ToolError with a human-readable message on bad input.

Design rule: tools do the computing, the LLM does the wording. The agent is
graded on whether its numbers match tool output — hallucinated figures are
eval failures, so nothing here is fuzzy.
"""

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from gridscout.export import GENERATION_ORDER, RENEWABLE
from gridscout.smard.filters import SERIES

TZ = ZoneInfo("Europe/Berlin")


class ToolError(Exception):
    pass


class GridTools:
    def __init__(self, data_dir: Path = Path("data"), reports_dir: Path = Path("reports")):
        self.data_dir = data_dir
        self.reports_dir = reports_dir
        self._cache: dict[str, pd.Series] = {}

    # -- series access -----------------------------------------------------

    def _series(self, name: str) -> pd.Series:
        if name not in self._cache:
            path = self.data_dir / f"{name}.parquet"
            if not path.exists():
                raise ToolError(f"series '{name}' is not available")
            df = pd.read_parquet(path)
            idx = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True).dt.tz_convert(TZ)
            self._cache[name] = pd.Series(df["value"].to_numpy(), index=idx, name=name)
        return self._cache[name]

    @staticmethod
    def _parse_day(day: str) -> date:
        try:
            return date.fromisoformat(day)
        except ValueError as exc:
            raise ToolError(f"'{day}' is not an ISO date (YYYY-MM-DD)") from exc

    def _day_slice(self, name: str, day: str) -> pd.Series:
        s = self._series(name)
        d = self._parse_day(day)
        sliced = s[[ts.date() == d for ts in s.index]].dropna()
        if sliced.empty:
            raise ToolError(
                f"no data for {name} on {day} "
                f"(available: {s.index.min().date()} to {s.index.max().date()})"
            )
        return sliced

    # -- tools -------------------------------------------------------------

    def get_price_day(self, day: str) -> dict:
        """Hourly day-ahead prices for one local day, EUR/MWh."""
        prices = self._day_slice("price_day_ahead", day)
        return {
            "day": day,
            "unit": "EUR/MWh",
            "hourly": {ts.strftime("%H:%M"): round(float(v), 2) for ts, v in prices.items()},
            "mean": round(float(prices.mean()), 2),
            "min": {"value": round(float(prices.min()), 2), "hour": int(prices.idxmin().hour)},
            "max": {"value": round(float(prices.max()), 2), "hour": int(prices.idxmax().hour)},
            "negative_hours": int((prices < 0).sum()),
        }

    def get_price_range_summary(self, start_day: str, end_day: str) -> dict:
        """Price statistics over an inclusive local-day range."""
        s = self._series("price_day_ahead").dropna()
        d0, d1 = self._parse_day(start_day), self._parse_day(end_day)
        if d1 < d0:
            raise ToolError("end_day is before start_day")
        if (d1 - d0).days > 400:
            raise ToolError("range too large (max 400 days)")
        mask = [(d0 <= ts.date() <= d1) for ts in s.index]
        window = s[mask]
        if window.empty:
            raise ToolError(f"no prices between {start_day} and {end_day}")
        return {
            "start_day": start_day,
            "end_day": end_day,
            "unit": "EUR/MWh",
            "n_hours": int(len(window)),
            "mean": round(float(window.mean()), 2),
            "min": {"value": round(float(window.min()), 2), "at": window.idxmin().isoformat()},
            "max": {"value": round(float(window.max()), 2), "at": window.idxmax().isoformat()},
            "negative_hours": int((window < 0).sum()),
        }

    def get_generation_mix_day(self, day: str) -> dict:
        """Daily generation totals per source (MWh) + renewables share."""
        totals: dict[str, float] = {}
        for name in GENERATION_ORDER:
            try:
                totals[name] = float(self._day_slice(name, day).sum())
            except ToolError:
                continue
        if not totals:
            raise ToolError(f"no generation data on {day}")
        total = sum(totals.values())
        renewables = sum(v for k, v in totals.items() if k in RENEWABLE)
        return {
            "day": day,
            "unit": "MWh",
            "by_source": {
                SERIES[k].label.removeprefix("Generation: "): round(v) for k, v in totals.items()
            },
            "total": round(total),
            "renewables_share": round(renewables / total, 3) if total else None,
        }

    def explain_price_context(self, day: str) -> dict:
        """Deterministic context for why prices looked the way they did:
        residual load (demand minus wind+solar) vs price, hour by hour."""
        prices = self._day_slice("price_day_ahead", day)
        context: dict = {"day": day, "price": {"mean": round(float(prices.mean()), 2)}}
        try:
            load = self._day_slice("load", day)
            solar = self._day_slice("gen_solar", day)
            wind = self._day_slice("gen_wind_onshore", day) + self._day_slice(
                "gen_wind_offshore", day
            )
            aligned = pd.DataFrame(
                {"price": prices, "load": load, "solar": solar, "wind": wind}
            ).dropna()
            aligned["residual_load"] = aligned["load"] - aligned["solar"] - aligned["wind"]
            corr = float(aligned["price"].corr(aligned["residual_load"]))
            cheapest = aligned.nsmallest(3, "price")
            priciest = aligned.nlargest(3, "price")
            context.update(
                {
                    "correlation_price_vs_residual_load": round(corr, 3),
                    "solar_peak_mwh": round(float(aligned["solar"].max())),
                    "wind_mean_mwh": round(float(aligned["wind"].mean())),
                    "cheapest_hours": [
                        {"hour": int(ts.hour), "price": round(float(r["price"]), 2),
                         "residual_load_mwh": round(float(r["residual_load"]))}
                        for ts, r in cheapest.iterrows()
                    ],
                    "priciest_hours": [
                        {"hour": int(ts.hour), "price": round(float(r["price"]), 2),
                         "residual_load_mwh": round(float(r["residual_load"]))}
                        for ts, r in priciest.iterrows()
                    ],
                    "note": "day-ahead prices track residual load: "
                    "high wind+solar -> low or negative prices",
                }
            )
        except ToolError:
            context["note"] = "generation context unavailable for this day (price data only)"
        return context

    def get_forecast_evaluation(self) -> dict:
        """Walk-forward eval metrics of the price forecast (honest, out-of-sample)."""
        path = self.reports_dir / "forecast_eval.json"
        if not path.exists():
            raise ToolError("forecast evaluation has not been produced yet")
        return json.loads(path.read_text())

    def get_battery_results(self) -> dict:
        """Battery arbitrage backtest results (what the forecast is worth in EUR)."""
        path = self.reports_dir / "battery_backtest.json"
        if not path.exists():
            raise ToolError("battery backtest has not been produced yet")
        return json.loads(path.read_text())

    def get_data_coverage(self) -> dict:
        """Which series exist and how fresh they are."""
        out = {}
        for name in SERIES:
            path = self.data_dir / f"{name}.parquet"
            if not path.exists():
                out[name] = {"available": False}
                continue
            s = self._series(name).dropna()
            out[name] = {
                "available": True,
                "from": s.index.min().date().isoformat(),
                "to": s.index.max().date().isoformat(),
            }
        return {"series": out, "now_local": datetime.now(TZ).isoformat(timespec="minutes")}


TOOL_SPECS = [
    {
        "name": "get_price_day",
        "description": "Hourly German day-ahead electricity prices for one day (EUR/MWh), "
        "with min/max/mean and negative-price hours.",
        "parameters": {"day": "ISO date YYYY-MM-DD"},
    },
    {
        "name": "get_price_range_summary",
        "description": "Price statistics (mean/min/max/negative hours) over a day range, "
        "max 400 days.",
        "parameters": {"start_day": "ISO date", "end_day": "ISO date"},
    },
    {
        "name": "get_generation_mix_day",
        "description": "German electricity generation per source for one day (MWh) and "
        "the renewables share.",
        "parameters": {"day": "ISO date YYYY-MM-DD"},
    },
    {
        "name": "explain_price_context",
        "description": "Why prices were high/low on a day: residual load vs price "
        "correlation, cheapest/priciest hours with context.",
        "parameters": {"day": "ISO date YYYY-MM-DD"},
    },
    {
        "name": "get_forecast_evaluation",
        "description": "Out-of-sample evaluation of the LightGBM day-ahead price forecast "
        "vs naive baselines (MAE, RMSE, skill).",
        "parameters": {},
    },
    {
        "name": "get_battery_results",
        "description": "Battery arbitrage backtest: revenue with model vs naive vs perfect "
        "foresight, capture rates.",
        "parameters": {},
    },
    {
        "name": "get_data_coverage",
        "description": "Which data series exist and their date coverage.",
        "parameters": {},
    },
]
