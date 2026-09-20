"""Deterministic, rule-written explanations of a market window.

Same numbers the charts show, assembled into a sentence by rule — no model, no
LLM, nothing that can hallucinate a driver that is not in the data. The agent
tool and the dashboard caption share this code so they cannot drift apart.

Language is English because the rest of the site is; the rules, not the prose,
are the interesting part.
"""

from dataclasses import dataclass

import pandas as pd

REQUIRED_COLUMNS = ("price", "load", "solar", "wind")
#: A day is called a spike day when its peak clears both bars — an absolute one
#: (so a calm expensive day does not qualify) and a relative one (so a cheap day
#: with one odd hour does).
SPIKE_ABS_EUR = 200.0
SPIKE_RATIO = 3.0


@dataclass(frozen=True)
class HourFact:
    hour: int
    price: float
    residual_load_mwh: float
    solar_mwh: float

    def as_dict(self) -> dict:
        return {
            "hour": self.hour,
            "price": round(self.price, 2),
            "residual_load_mwh": round(self.residual_load_mwh),
        }


def align(price: pd.Series, load: pd.Series, solar: pd.Series, wind: pd.Series) -> pd.DataFrame:
    """One frame, hours where every input exists, plus residual load."""
    frame = pd.DataFrame({"price": price, "load": load, "solar": solar, "wind": wind}).dropna()
    frame["residual_load"] = frame["load"] - frame["solar"] - frame["wind"]
    return frame


def window_facts(frame: pd.DataFrame) -> dict:
    """Structured facts about an aligned hourly window (see `align`)."""
    missing = [c for c in REQUIRED_COLUMNS if c not in frame]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    if frame.empty:
        raise ValueError("no overlapping hours")
    if "residual_load" not in frame:
        frame = frame.assign(residual_load=frame["load"] - frame["solar"] - frame["wind"])

    correlation = frame["price"].corr(frame["residual_load"])
    cheapest = _facts(frame.nsmallest(3, "price"))
    priciest = _facts(frame.nlargest(3, "price"))
    mean_price = float(frame["price"].mean())
    max_price = float(frame["price"].max())
    return {
        "n_hours": int(len(frame)),
        "mean_price": round(mean_price, 2),
        "min_price": round(float(frame["price"].min()), 2),
        "max_price": round(max_price, 2),
        "spread": round(max_price - float(frame["price"].min()), 2),
        "negative_hours": int((frame["price"] < 0).sum()),
        "solar_peak_mwh": round(float(frame["solar"].max())),
        "wind_mean_mwh": round(float(frame["wind"].mean())),
        # a constant series gives NaN, which is not valid JSON
        "correlation_price_vs_residual_load": (
            None if pd.isna(correlation) else round(float(correlation), 3)
        ),
        "cheapest_hours": [h.as_dict() for h in cheapest],
        "priciest_hours": [h.as_dict() for h in priciest],
        "is_spike": max_price >= SPIKE_ABS_EUR and max_price >= SPIKE_RATIO * abs(mean_price),
        "_cheapest": cheapest,
        "_priciest": priciest,
    }


def caption(facts: dict) -> str:
    """One or two sentences, written by rule from `window_facts`."""
    low, high = facts["_cheapest"][0], facts["_priciest"][0]
    head = (
        f"Cheapest hour {_hh(low.hour)} at {low.price:.2f} EUR/MWh with "
        f"{_gw(low.solar_mwh)} GW of solar and {_gw(low.residual_load_mwh)} GW residual load; "
        f"most expensive {_hh(high.hour)} at {high.price:.2f} EUR/MWh at "
        f"{_gw(high.residual_load_mwh)} GW residual load."
    )
    parts = [head]
    if facts["negative_hours"]:
        parts.append(
            f"{facts['negative_hours']} hour"
            f"{'s' if facts['negative_hours'] > 1 else ''} cleared below zero — "
            "renewables covered more than the grid could absorb."
        )
    if facts["is_spike"]:
        parts.append(
            f"Peak is {facts['max_price'] / max(abs(facts['mean_price']), 1e-9):.1f}x the window "
            "mean: a scarcity hour, not a normal evening ramp."
        )
    correlation = facts["correlation_price_vs_residual_load"]
    if correlation is not None:
        direction = "tracks" if correlation > 0 else "runs against"
        parts.append(
            f"Across the window the price {direction} residual load "
            f"(correlation {correlation:+.2f})."
        )
    return " ".join(parts)


def describe(frame: pd.DataFrame) -> dict:
    """Facts plus caption, with the private helper keys stripped for JSON."""
    facts = window_facts(frame)
    return {**{k: v for k, v in facts.items() if not k.startswith("_")}, "caption": caption(facts)}


def _facts(rows: pd.DataFrame) -> list[HourFact]:
    return [
        HourFact(
            hour=int(ts.hour),
            price=float(row["price"]),
            residual_load_mwh=float(row["residual_load"]),
            solar_mwh=float(row["solar"]),
        )
        for ts, row in rows.iterrows()
    ]


def _hh(hour: int) -> str:
    return f"{hour:02d}:00"


def _gw(mwh: float) -> str:
    return f"{mwh / 1000:.1f}"
