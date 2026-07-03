import json

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


def test_export_site_data_skips_missing_reports(data_dir, tmp_path):
    out = tmp_path / "out"
    written = export_site_data(data_dir, tmp_path / "no-reports", out)
    assert "market.json" in written
    assert "forecast.json" not in written  # no eval report yet
    payload = json.loads((out / "market.json").read_text())
    assert payload["kpis"]["latest_price_eur_mwh"] is not None
