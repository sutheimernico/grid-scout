from datetime import UTC, datetime

import pandas as pd
import pytest

from gridscout.smard.client import SmardClient
from gridscout.smard.filters import SERIES
from gridscout.smard.ingest import ingest_series, series_path
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
