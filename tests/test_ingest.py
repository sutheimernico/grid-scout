from datetime import UTC, datetime

import pandas as pd
import pytest
from typer.testing import CliRunner

from gridscout.cli import app
from gridscout.smard.client import SmardClient
from gridscout.smard.filters import SERIES
from gridscout.smard.ingest import ingest_all, ingest_series, series_path
from tests.conftest import HOUR_MS, WEEK1, WEEK2, WEEK3, make_week

START = datetime(2023, 1, 1, tzinfo=UTC)
PRICE = SERIES["price_day_ahead"]


def run_ingest(fake_smard, tmp_path):
    with SmardClient(
        cache_dir=tmp_path / "cache", transport=fake_smard.transport, request_delay_s=0
    ) as client:
        return ingest_series(client, PRICE, tmp_path / "data", START)


@pytest.fixture
def three_weeks(fake_smard):
    fake_smard.set_week(4169, WEEK1, make_week(WEEK1, 10))
    fake_smard.set_week(4169, WEEK2, make_week(WEEK2, 20))
    fake_smard.set_week(4169, WEEK3, make_week(WEEK3, 30, n_null_tail=24))
    return fake_smard


def test_backfill_writes_parquet(three_weeks, tmp_path):
    result = run_ingest(three_weeks, tmp_path)
    df = pd.read_parquet(series_path(tmp_path / "data", "price_day_ahead"))
    assert result.weeks_fetched == 3
    # 3 weeks minus the 24 unpublished trailing nulls
    assert len(df) == 3 * 168 - 24
    assert df["timestamp_ms"].is_monotonic_increasing
    assert df["value"].notna().all()


def test_rerun_only_refetches_trailing_weeks(three_weeks, tmp_path):
    run_ingest(three_weeks, tmp_path)
    three_weeks.requests.clear()
    result = run_ingest(three_weeks, tmp_path)
    data_requests = [r for r in three_weeks.requests if "index" not in r]
    # trailing 2 weeks are always refreshed; week 1 must be skipped entirely
    assert result.weeks_fetched == 2
    assert all(str(WEEK1) not in r for r in data_requests)


def test_revised_values_win(three_weeks, tmp_path):
    run_ingest(three_weeks, tmp_path)
    three_weeks.set_week(4169, WEEK3, make_week(WEEK3, 999))
    run_ingest(three_weeks, tmp_path)
    df = pd.read_parquet(series_path(tmp_path / "data", "price_day_ahead"))
    week3 = df[df["timestamp_ms"] >= WEEK3]
    assert week3["value"].iloc[0] == 999.0
    assert len(week3) == 168  # previously-null tail now published


def test_interior_nulls_are_kept(fake_smard, tmp_path):
    week = make_week(WEEK1, 10)
    week[5][1] = None  # a real historical gap, not an unpublished tail
    fake_smard.set_week(4169, WEEK1, week)
    fake_smard.set_week(4169, WEEK2, make_week(WEEK2, 20))
    run_ingest(fake_smard, tmp_path)
    df = pd.read_parquet(series_path(tmp_path / "data", "price_day_ahead"))
    assert df["value"].isna().sum() == 1
    assert df.loc[df["value"].isna(), "timestamp_ms"].iloc[0] == WEEK1 + 5 * HOUR_MS


def test_validation_failure_raises(fake_smard, tmp_path):
    week = make_week(WEEK1, 10)
    week[3][0] = week[2][0]  # duplicate timestamp
    fake_smard.set_week(4169, WEEK1, week)
    with pytest.raises(ValueError, match="validation failed"):
        run_ingest(fake_smard, tmp_path)


class TestFaultIsolation:
    """One glitchy SMARD response must not abort the whole 3-hourly run."""

    NAMES = [
        "price_day_ahead",
        "load",
        "gen_solar",
        "gen_wind_onshore",
        "gen_biomass",
    ]

    def _client(self, fake_smard, tmp_path):
        return SmardClient(
            cache_dir=tmp_path / "cache", transport=fake_smard.transport, request_delay_s=0
        )

    def _stub_weeks(self, fake_smard):
        # WEEK1 starts before the shallow-history cutoff, so stub from WEEK2 on —
        # otherwise the generation series would legitimately come back empty.
        for name in self.NAMES:
            for week in (WEEK2, WEEK3):
                fake_smard.set_week(SERIES[name].filter_id, week, make_week(week, 10))

    def test_failing_series_does_not_stop_the_rest(self, fake_smard, tmp_path, monkeypatch):
        self._stub_weeks(fake_smard)
        broken = self.NAMES[2]
        real = ingest_series

        def flaky(client, spec, data_dir, start):
            if spec.name == broken:
                raise RuntimeError("SMARD returned garbage")
            return real(client, spec, data_dir, start)

        monkeypatch.setattr("gridscout.smard.ingest.ingest_series", flaky)
        with self._client(fake_smard, tmp_path) as client:
            run = ingest_all(client, tmp_path / "data", names=self.NAMES)

        assert not run.ok
        assert [name for name, _ in run.failures] == [broken]
        assert "SMARD returned garbage" in run.failures[0][1]
        # every other series was still attempted and written
        assert [r.series for r in run.results] == [n for n in self.NAMES if n != broken]
        for name in self.NAMES:
            written = series_path(tmp_path / "data", name).exists()
            assert written is (name != broken)

    def test_all_good_run_reports_no_failures(self, fake_smard, tmp_path):
        self._stub_weeks(fake_smard)
        with self._client(fake_smard, tmp_path) as client:
            run = ingest_all(client, tmp_path / "data", names=self.NAMES)
        assert run.ok
        assert len(run.results) == len(self.NAMES)

    def test_cli_exits_non_zero_after_attempting_everything(
        self, fake_smard, tmp_path, monkeypatch
    ):
        self._stub_weeks(fake_smard)
        monkeypatch.setattr(
            "gridscout.cli.SmardClient",
            lambda **kw: SmardClient(
                cache_dir=tmp_path / "cache", transport=fake_smard.transport, request_delay_s=0
            ),
        )
        real = ingest_series

        def flaky(client, spec, data_dir, start):
            if spec.name == "gen_solar":
                raise RuntimeError("boom")
            return real(client, spec, data_dir, start)

        monkeypatch.setattr("gridscout.smard.ingest.ingest_series", flaky)
        result = CliRunner().invoke(
            app,
            ["ingest", "--data-dir", str(tmp_path / "data")]
            + [arg for name in self.NAMES for arg in ("-s", name)],
        )
        assert result.exit_code == 1
        assert "gen_solar: FAILED" in result.output
        assert "1 of 5 series failed" in result.output
        assert "price_day_ahead:" in result.output  # the healthy ones still ran
