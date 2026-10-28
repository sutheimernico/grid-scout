import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gridscout.export import export_battery, export_health, export_market, export_site_data
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


class TestBatteryExport:
    def _reports(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        (reports / "battery_backtest.json").write_text(json.dumps({"n_days": 2}))
        pd.DataFrame(
            {"local_day": ["2025-01-01", "2025-01-02"], "perfect": [10.0, 20.0],
             "model": [8.0, 18.0], "naive": [7.0, 15.0]}
        ).to_parquet(reports / "battery_daily.parquet")
        return reports

    def test_sensitivity_is_absent_until_the_weekly_sweep_has_run(self, tmp_path):
        payload = export_battery(self._reports(tmp_path))
        assert "sensitivity" not in payload
        assert payload["daily"]["cumulative_model"] == [8.0, 26.0]

    def test_sensitivity_is_passed_through_when_present(self, tmp_path):
        reports = self._reports(tmp_path)
        sweep = {"generated_utc": "2026-09-28T02:30:00+00:00", "cells": [{"duration_h": 2}]}
        (reports / "battery_sensitivity.json").write_text(json.dumps(sweep))
        assert export_battery(reports)["sensitivity"] == sweep


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
        # the weekly sensitivity sweep is watched like the other weekly reports
        assert health["reports"]["battery_sensitivity.json"]["status"] == "missing"
        assert health["reports"]["battery_sensitivity.json"]["cadence_days"] == 7

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


class TestUptime:
    def test_counts_pipeline_commits_per_day_from_the_real_history(self):
        """The heartbeat panel is only worth showing if it reads the real repo."""
        from gridscout.export import export_uptime

        repo = Path(__file__).resolve().parent.parent
        shallow = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=repo, capture_output=True, text=True, check=False,
        ).stdout.strip()
        if shallow != "false":
            # CI's default checkout has one commit; the pipeline itself fetches the
            # full history, and the merge test below covers the shallow case.
            pytest.skip("needs the full git history (shallow or no git checkout)")
        uptime = export_uptime(repo)
        assert uptime["first_day"] == "2026-07-04"  # the day the pipeline went live
        assert uptime["totals"]["runs"] > 400
        assert uptime["totals"]["days"] == len(uptime["days"])
        # dense series: every calendar day present exactly once, gaps included
        dates = [d["date"] for d in uptime["days"]]
        assert dates == sorted(dates)
        assert len(set(dates)) == len(dates)

    def test_merges_the_previous_calendar_so_a_shallow_clone_cannot_lose_history(
        self, tmp_path
    ):
        from gridscout.export import export_uptime

        previous = tmp_path / "uptime.json"
        previous.write_text(
            json.dumps(
                {"days": [{"date": "2020-01-01", "runs": 8}, {"date": "2020-01-03", "runs": 3}]}
            )
        )
        # a directory that is not a git repo stands in for a checkout git cannot read
        uptime = export_uptime(tmp_path, previous)
        by_date = {d["date"]: d["runs"] for d in uptime["days"]}
        assert by_date["2020-01-01"] == 8
        assert by_date["2020-01-02"] == 0  # the gap is kept, not smoothed away
        assert by_date["2020-01-03"] == 3
        assert uptime["totals"]["longest_silent_streak_days"] >= 1

    def test_no_history_at_all_means_no_artifact(self, tmp_path):
        from gridscout.export import export_uptime

        with pytest.raises(FileNotFoundError):
            export_uptime(tmp_path, tmp_path / "nothing.json")


def test_health_entries_carry_a_human_label(data_dir):
    health = export_health(data_dir)
    assert health["series"]["price_day_ahead"]["label"] == "Day-ahead price DE/LU"
    assert health["series"]["forecast_solar"]["label"]  # missing series keep it too


class TestAgentExport:
    def _report(self, passed, n):
        return {
            "model": "m",
            "generated_utc": "2026-10-28T12:00:00+00:00",
            "n": n,
            "passed": passed,
            "pass_rate": passed / n,
            "by_type": {"factual": {"n": n, "passed": passed, "pass_rate": passed / n}},
            "grading": "programmatic",
            "results": [
                {
                    "type": "factual",
                    "question": "q",
                    "answer": "a",
                    "gold": "1",
                    "passed": True,
                    "tool_calls": [],
                }
            ],
        }

    def test_dated_and_holdout_reported_when_present(self, tmp_path):
        from gridscout.export import export_agent

        (tmp_path / "agent_eval.json").write_text(json.dumps(self._report(9, 10)))
        assert "holdout" not in export_agent(tmp_path)
        (tmp_path / "agent_eval_holdout.json").write_text(json.dumps(self._report(6, 10)))
        out = export_agent(tmp_path)
        assert out["generated_utc"].startswith("2026-10-28")
        assert out["holdout"]["pass_rate"] == 0.6
