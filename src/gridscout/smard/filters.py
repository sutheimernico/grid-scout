"""Registry of SMARD chart_data filter IDs.

Every ID below was probed live against the API on 2026-07-03 (hourly resolution,
region DE, history back to 2014-12-29). Do not add IDs from blog posts without
probing them: the bundesAPI OpenAPI spec itself disagrees between enum (126) and
description (125) for the solar forecast — 125 is correct, 126 is a negated
wind+solar aggregate.
"""

from dataclasses import dataclass
from enum import StrEnum


class Kind(StrEnum):
    PRICE = "price"
    LOAD = "load"
    GENERATION = "generation"
    FORECAST = "forecast"


@dataclass(frozen=True)
class SeriesSpec:
    name: str
    filter_id: int
    kind: Kind
    label: str
    unit: str


_SPECS = [
    # Target + market context
    SeriesSpec("price_day_ahead", 4169, Kind.PRICE, "Day-ahead price DE/LU", "EUR/MWh"),
    # Consumption
    SeriesSpec("load", 410, Kind.LOAD, "Grid load (total consumption)", "MWh"),
    SeriesSpec("residual_load", 4359, Kind.LOAD, "Residual load", "MWh"),
    # Day-ahead available forecasts (leakage-safe model features)
    SeriesSpec("forecast_generation_total", 122, Kind.FORECAST, "Forecast: total gen.", "MWh"),
    SeriesSpec("forecast_wind_onshore", 123, Kind.FORECAST, "Forecast: wind onshore", "MWh"),
    SeriesSpec("forecast_wind_offshore", 3791, Kind.FORECAST, "Forecast: wind offshore", "MWh"),
    SeriesSpec("forecast_solar", 125, Kind.FORECAST, "Forecast: photovoltaics", "MWh"),
    # Realized generation mix (dashboard)
    SeriesSpec("gen_lignite", 1223, Kind.GENERATION, "Generation: lignite", "MWh"),
    SeriesSpec("gen_nuclear", 1224, Kind.GENERATION, "Generation: nuclear", "MWh"),
    SeriesSpec("gen_wind_offshore", 1225, Kind.GENERATION, "Generation: wind offshore", "MWh"),
    SeriesSpec("gen_hydro", 1226, Kind.GENERATION, "Generation: hydro", "MWh"),
    SeriesSpec("gen_other_conventional", 1227, Kind.GENERATION, "Generation: other conv.", "MWh"),
    SeriesSpec("gen_other_renewable", 1228, Kind.GENERATION, "Generation: other renewable", "MWh"),
    SeriesSpec("gen_biomass", 4066, Kind.GENERATION, "Generation: biomass", "MWh"),
    SeriesSpec("gen_wind_onshore", 4067, Kind.GENERATION, "Generation: wind onshore", "MWh"),
    SeriesSpec("gen_solar", 4068, Kind.GENERATION, "Generation: photovoltaics", "MWh"),
    SeriesSpec("gen_hard_coal", 4069, Kind.GENERATION, "Generation: hard coal", "MWh"),
    SeriesSpec("gen_pumped_storage", 4070, Kind.GENERATION, "Generation: pumped storage", "MWh"),
    SeriesSpec("gen_gas", 4071, Kind.GENERATION, "Generation: natural gas", "MWh"),
]

SERIES: dict[str, SeriesSpec] = {s.name: s for s in _SPECS}

# Model-relevant series get deep history; the generation mix only feeds the
# dashboard and stays shallow to keep backfill polite (~1.5k fewer requests).
DEEP_HISTORY_NAMES = [
    "price_day_ahead",
    "load",
    "residual_load",
    "forecast_generation_total",
    "forecast_wind_onshore",
    "forecast_wind_offshore",
    "forecast_solar",
]
