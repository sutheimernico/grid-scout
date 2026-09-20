import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gridscout.export import export_health, export_market, export_site_data
from gridscout.smard.filters import SERIES
from tests.conftest import HOUR_MS


def write_series(data_dir, name, values, start_ms=1750000000000 - 200 * HOUR_MS):
    data_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {"timestamp_ms": [start_ms + i * HOUR_MS for i in range(len(values))], "value": values}
    ).to_parquet(data_dir / f"{name}.parquet")


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    n = 200
    rng = np.random.default_rng(3)
    write_series(d, "price_day_ahead", rng.normal(90, 40, n))
    write_series(d, "load", rng.uniform(40_000, 60_000, n))
    for name in SERIES:
        if name.startswith("gen_"):
            write_series(d, name, rng.uniform(0, 10_000, n))
    return d


def test_export_market_structure(data_dir):
    market = export_market(data_dir, days=3)
    assert set(market["kpis"]) >= {
        "latest_price_eur_mwh",
        "negative_price_hours_ytd",
        "renewables_share_last_24h",
    }
    hourly = market["hourly"]
    assert len(hourly["timestamps"]) == len(hourly["price"]) == len(hourly["load"])
    assert 0 <= market["kpis"]["renewables_share_last_24h"] <= 1
    for values in hourly["generation"].values():
        assert len(values) == len(hourly["timestamps"])


def test_export_health_flags_missing_and_stale(data_dir):
    health = export_health(data_dir)
    # fixture timestamps are historic -> everything present must be stale
    assert health["series"]["price_day_ahead"]["status"] == "stale"
    assert health["series"]["forecast_solar"]["status"] == "missing"


def test_discontinued_series_is_not_a_stale_alarm(data_dir):
    """gen_nuclear can never be fresh again — it must not sit in the panel as a
    permanent red row next to genuinely broken series."""
    health = export_health(data_dir)
    nuclear = health["series"]["gen_nuclear"]
    assert nuclear["status"] == "discontinued"
    assert "phase-out" in nuclear["note"]
    # the same fixture age still alarms for a series that is supposed to update
    assert health["series"]["gen_solar"]["status"] == "stale"


def test_discontinued_status_holds_on_the_real_ingested_data():
    """Regression guard against the live false alarm: on the repo's actual
    pipeline data, no discontinued series may report as stale. Independent of
    how fresh the rest of the data is, so a pipeline outage cannot flip it."""
    data_dir = Path(__file__).resolve().parent.parent / "data"
    declared = [name for name, spec in SERIES.items() if spec.discontinued]
    present = [n for n in declared if (data_dir / f"{n}.parquet").exists()]
    if not present:
        pytest.skip("no ingested data for discontinued series in this checkout")
    health = export_health(data_dir)
    assert {health["series"][n]["status"] for n in present} == {"discontinued"}


def test_export_site_data_skips_missing_reports(data_dir, tmp_path):
    out = tmp_path / "out"
    written = export_site_data(data_dir, tmp_path / "no-reports", out)
    assert "market.json" in written
    assert "forecast.json" not in written  # no eval report yet
    payload = json.loads((out / "market.json").read_text())
    assert payload["kpis"]["latest_price_eur_mwh"] is not None
