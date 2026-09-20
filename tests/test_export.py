import json
from datetime import UTC, datetime, timedelta
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


class TestReportFreshness:
    """A dead weekly eval must not hide behind fresh raw data."""

    def _write(self, reports_dir, name, payload):
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / name).write_text(json.dumps(payload))

    def _stamp(self, days_ago):
        return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat(timespec="seconds")

    def test_weekly_report_ages_then_goes_overdue(self, data_dir, tmp_path):
        reports = tmp_path / "reports"
        self._write(reports, "forecast_eval.json", {"generated_utc": self._stamp(10)})
        self._write(reports, "battery_backtest.json", {"generated_utc": self._stamp(20)})
        health = export_health(data_dir, reports)

        assert health["reports"]["forecast_eval.json"]["status"] == "aging"
        assert health["reports"]["forecast_eval.json"]["age_days"] == pytest.approx(10, abs=0.1)
        assert health["reports"]["battery_backtest.json"]["status"] == "overdue"
        # raw series are judged independently of the reports
        assert health["series"]["gen_solar"]["status"] == "stale"

    def test_fresh_report_is_ok_and_manual_report_never_alarms(self, data_dir, tmp_path):
        reports = tmp_path / "reports"
        self._write(reports, "forecast_eval.json", {"generated_utc": self._stamp(2)})
        # the agent eval needs a local Ollama run — it has no cadence to miss
        self._write(reports, "agent_eval.json", {"generated_utc": self._stamp(400)})
        health = export_health(data_dir, reports)
        assert health["reports"]["forecast_eval.json"]["status"] == "ok"
        assert health["reports"]["agent_eval.json"]["status"] == "manual"

    def test_missing_and_unstamped_reports_are_distinguished(self, data_dir, tmp_path):
        reports = tmp_path / "reports"
        self._write(reports, "forecast_eval.json", {"no": "timestamp"})
        health = export_health(data_dir, reports)
        # guessing from file mtime would be a false green in CI (git drops mtimes)
        assert health["reports"]["forecast_eval.json"]["status"] == "unknown"
        assert health["reports"]["battery_backtest.json"]["status"] == "missing"

    def test_health_without_reports_dir_stays_backwards_compatible(self, data_dir):
        assert export_health(data_dir)["reports"] == {}

    def test_export_site_data_wires_the_reports_dir_through(self, data_dir, tmp_path):
        reports = tmp_path / "reports"
        self._write(reports, "forecast_eval.json", {"generated_utc": self._stamp(1)})
        out = tmp_path / "out"
        export_site_data(data_dir, reports, out)
        payload = json.loads((out / "health.json").read_text())
        assert payload["reports"]["forecast_eval.json"]["status"] == "ok"


class TestForwardLedgerExport:
    def _record(self, day, scored):
        return {
            "target_date": day,
            "generated_at_utc": f"{day}T09:23:00+00:00",
            "information_cutoff_utc": f"{day}T00:00:00+00:00",
            "feature_set": "pre_auction",
            "model_version": "abc123",
            "train_days": 540,
            "train_rows": 12959,
            "timestamps_utc": [f"{day}T0{h}:00:00+00:00" for h in range(3)],
            "hours_local": [0, 1, 2],
            "pred_model": [100.0, 90.0, 80.0],
            "pred_naive": [95.0, 85.0, 75.0],
            "pred_snaive7": [50.0, 50.0, 50.0],
            "scored_at_utc": f"{day}T23:00:00+00:00" if scored else None,
            "actual": [99.0, 91.0, 84.0] if scored else None,
            "mae_model": 2.0 if scored else None,
            "mae_naive": 5.0 if scored else None,
            "mae_snaive7": 41.0 if scored else None,
            "n_hours_scored": 3 if scored else None,
        }

    def test_export_shapes_the_track_record(self, tmp_path):
        from gridscout.export import export_forward_ledger
        from gridscout.forecast.forward import write_ledger

        reports = tmp_path / "reports"
        write_ledger(
            reports, [self._record("2026-09-18", True), self._record("2026-09-19", False)]
        )
        payload = export_forward_ledger(reports)
        assert payload["summary"]["n_scored"] == 1
        assert payload["summary"]["n_pending"] == 1
        assert payload["summary"]["cumulative"]["mae_model"] == 2.0
        assert [d["target_date"] for d in payload["days"]] == ["2026-09-18", "2026-09-19"]
        # the newest record drives the chart, pending or not
        assert payload["latest"]["target_date"] == "2026-09-19"
        assert payload["latest"]["actual"] is None

    def test_site_export_skips_the_ledger_until_it_exists(self, data_dir, tmp_path):
        written = export_site_data(data_dir, tmp_path / "no-reports", tmp_path / "out")
        assert "forward_ledger.json" not in written
