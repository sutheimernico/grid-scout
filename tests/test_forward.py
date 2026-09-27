from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from gridscout.cli import app
from gridscout.forecast import forward
from gridscout.forecast.features import FULL, PRE_AUCTION, load_series_frame
from gridscout.forecast.forward import (
    ForwardConfig,
    NotForecastable,
    append_record,
    assert_no_target_day_leakage,
    day_index_utc,
    day_start_utc,
    extend_to_delivery_day,
    gate_closure_utc,
    make_prediction,
    next_delivery_day,
    read_ledger,
    score_ledger,
    summarize_ledger,
    window_stats,
)

HOUR_MS = 3_600_000
START = pd.Timestamp("2025-01-01 00:00", tz="Europe/Berlin").tz_convert("UTC")
DAYS = 220
TARGET_DAY = (START + pd.Timedelta(days=DAYS - 1)).tz_convert("Europe/Berlin").date()
FAST = ForwardConfig(train_days=200, n_estimators=20)


EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


def _write(data_dir, name, index, values):
    data_dir.mkdir(parents=True, exist_ok=True)
    # go through a Timedelta, not astype("int64"): the index resolution is not
    # guaranteed to be nanoseconds and the silent factor-1000 error is nasty
    pd.DataFrame(
        {"timestamp_ms": (index - EPOCH) // pd.Timedelta("1ms"), "value": values}
    ).to_parquet(data_dir / f"{name}.parquet", index=False)


def _index(days=DAYS):
    return pd.date_range(START, periods=days * 24, freq="h", tz="UTC")


def build_data(tmp_path, prices_include_target=False):
    """Synthetic SMARD-shaped data.

    By default the price series stops at the German midnight before TARGET_DAY —
    the live situation the daily job runs in. With prices_include_target the
    delivery day is already auctioned.
    """
    data_dir = tmp_path / "data"
    idx = _index()
    rng = np.random.default_rng(11)
    solar = 20_000 * np.clip(np.sin((np.arange(len(idx)) % 24 - 6) / 12 * np.pi), 0, None)
    wind = rng.uniform(1_000, 30_000, len(idx))
    load = 45_000 + 8_000 * np.sin(np.arange(len(idx)) / 24 * 2 * np.pi)
    # price is a learnable function of residual load plus noise
    price = (load - solar - wind) / 400 + rng.normal(0, 4, len(idx))

    _write(data_dir, "load", idx, load)
    _write(data_dir, "forecast_solar", idx, solar)
    _write(data_dir, "forecast_wind_onshore", idx, wind * 0.7)
    _write(data_dir, "forecast_wind_offshore", idx, wind * 0.3)
    _write(data_dir, "forecast_generation_total", idx, solar + wind)
    published = idx if prices_include_target else idx[idx < day_start_utc(TARGET_DAY)]
    _write(data_dir, "price_day_ahead", published, price[: len(published)])
    return data_dir, idx, price


@pytest.fixture
def data(tmp_path):
    return build_data(tmp_path)


#: The morning of the day before TARGET_DAY — the moment the daily job runs.
MORNING_BEFORE = datetime.combine(TARGET_DAY - timedelta(days=1), datetime.min.time(), UTC).replace(
    hour=6
)


@pytest.fixture(autouse=True)
def pinned_clock(monkeypatch):
    """TARGET_DAY lies in the past, so the real clock would always be past its
    auction. Pin it to the morning before; tests that need another time re-pin."""
    monkeypatch.setattr(forward, "utc_now", lambda: MORNING_BEFORE)


class TestCalendar:
    def test_next_delivery_day_is_tomorrow_in_german_market_time(self):
        # 23:30 UTC in summer is already the next day in Berlin
        now = datetime(2026, 6, 1, 23, 30, tzinfo=UTC)
        assert next_delivery_day(now) == date(2026, 6, 3)
        assert next_delivery_day(datetime(2026, 6, 1, 8, 0, tzinfo=UTC)) == date(2026, 6, 2)

    @pytest.mark.parametrize(
        ("day", "hours"),
        [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25), (date(2026, 6, 1), 24)],
    )
    def test_day_index_covers_dst_days_exactly(self, day, hours):
        assert len(day_index_utc(day)) == hours

    def test_extend_adds_the_delivery_day_rows(self, data):
        _, idx, _ = data
        raw = pd.DataFrame({"a": np.zeros(len(idx))}, index=idx)
        day = (idx[-1] + pd.Timedelta(days=1)).tz_convert("Europe/Berlin").date()
        extended = extend_to_delivery_day(raw, day)
        covered = extended.index.tz_convert("Europe/Berlin").date == day
        assert covered.sum() == 24
        assert extended.loc[covered, "a"].isna().all()
        assert extended.index.is_monotonic_increasing


class TestLeakageGuard:
    def test_pre_auction_features_never_touch_the_delivery_day(self, data):
        data_dir, _, _ = data
        raw = extend_to_delivery_day(
            load_series_frame(data_dir, PRE_AUCTION.raw_series), TARGET_DAY
        )
        assert_no_target_day_leakage(raw, TARGET_DAY, PRE_AUCTION)  # must not raise

    def test_guard_trips_on_a_feature_set_that_reads_the_delivery_day(self, data):
        data_dir, _, _ = data
        raw = extend_to_delivery_day(load_series_frame(data_dir, FULL.raw_series), TARGET_DAY)
        # FULL uses the generation forecast AT the target hour — legitimate for the
        # backtest, fatal for a live pre-auction claim. The guard must say so.
        with pytest.raises(NotForecastable, match="leakage guard tripped"):
            assert_no_target_day_leakage(raw, TARGET_DAY, FULL)


class TestPrediction:
    def test_records_one_prediction_per_hour_with_both_baselines(self, data):
        data_dir, _, _ = data
        record = make_prediction(data_dir, TARGET_DAY, FAST)
        assert record["target_date"] == TARGET_DAY.isoformat()
        assert record["feature_set"] == "pre_auction"
        assert len(record["pred_model"]) == 24
        assert len(record["pred_naive"]) == 24
        assert len(record["pred_snaive7"]) == 24
        assert record["scored_at_utc"] is None
        assert record["train_rows"] >= 24 * 90
        assert record["information_cutoff_utc"].startswith(
            str(TARGET_DAY - timedelta(days=1))
        ) or record["information_cutoff_utc"].startswith(str(TARGET_DAY))

    def test_record_carries_the_time_it_was_made(self, data):
        data_dir, _, _ = data
        record = make_prediction(data_dir, TARGET_DAY, FAST)
        assert record["generated_at_utc"] == MORNING_BEFORE.isoformat(timespec="seconds")

    def test_refuses_once_the_auction_has_closed(self, data, monkeypatch):
        # prices are not public yet, so only the clock can tell this is too late
        data_dir, _, _ = data
        gate = gate_closure_utc(TARGET_DAY).to_pydatetime()
        monkeypatch.setattr(forward, "utc_now", lambda: gate)
        with pytest.raises(NotForecastable, match="auction .* closed"):
            make_prediction(data_dir, TARGET_DAY, FAST)
        monkeypatch.setattr(forward, "utc_now", lambda: gate - timedelta(minutes=1))
        assert make_prediction(data_dir, TARGET_DAY, FAST)["target_date"] == str(TARGET_DAY)

    def test_refuses_when_the_gate_passes_while_the_model_trains(self, data, monkeypatch):
        data_dir, _, _ = data
        gate = gate_closure_utc(TARGET_DAY).to_pydatetime()
        clock = iter([gate - timedelta(seconds=5), gate + timedelta(seconds=30)])
        monkeypatch.setattr(forward, "utc_now", lambda: next(clock))
        with pytest.raises(NotForecastable, match="closed"):
            make_prediction(data_dir, TARGET_DAY, FAST)

    @pytest.mark.parametrize(
        ("day", "expected_utc"),
        [
            (date(2026, 7, 2), "2026-07-01T10:00:00+00:00"),  # CEST, UTC+2
            (date(2026, 12, 2), "2026-12-01T11:00:00+00:00"),  # CET, UTC+1
            (date(2026, 10, 26), "2026-10-25T11:00:00+00:00"),  # D-1 is the switch day
        ],
    )
    def test_gate_closure_is_noon_german_time_on_the_day_before(self, day, expected_utc):
        assert gate_closure_utc(day).isoformat() == expected_utc

    def test_refuses_once_the_prices_are_public(self, tmp_path):
        data_dir, _, _ = build_data(tmp_path, prices_include_target=True)
        with pytest.raises(NotForecastable, match="already published"):
            make_prediction(data_dir, TARGET_DAY, FAST)

    def test_refuses_when_the_delivery_day_has_no_inputs_yet(self, data):
        data_dir, _, _ = data
        far = TARGET_DAY + timedelta(days=3)
        with pytest.raises(NotForecastable, match="no complete feature rows"):
            make_prediction(data_dir, far, FAST)

    def test_refuses_without_enough_training_history(self, tmp_path):
        data_dir, _, _ = build_data(tmp_path)
        with pytest.raises(NotForecastable, match="training rows"):
            make_prediction(data_dir, TARGET_DAY, ForwardConfig(train_days=30, n_estimators=10))


class TestLedger:
    def test_pending_then_scored(self, data, tmp_path):
        data_dir, idx, price = data
        reports = tmp_path / "reports"
        append_record(reports, make_prediction(data_dir, TARGET_DAY, FAST))

        assert score_ledger(data_dir, reports) == []  # the day has not cleared yet
        assert read_ledger(reports)[0]["scored_at_utc"] is None

        _write(data_dir, "price_day_ahead", idx, price)  # auction results arrive
        scored = score_ledger(data_dir, reports)
        assert len(scored) == 1
        record = read_ledger(reports)[0]
        assert record["scored_at_utc"] is not None
        assert record["n_hours_scored"] == 24
        assert record["mae_model"] > 0
        expected = float(
            np.mean(np.abs(np.array(record["actual"]) - np.array(record["pred_naive"])))
        )
        assert record["mae_naive"] == pytest.approx(expected, abs=0.01)

    def test_rerun_replaces_a_pending_record_but_never_a_scored_one(self, data, tmp_path):
        data_dir, idx, price = data
        reports = tmp_path / "reports"
        first = make_prediction(data_dir, TARGET_DAY, FAST)
        append_record(reports, first)

        pending_again = {**first, "generated_at_utc": "2099-01-01T00:00:00+00:00"}
        assert append_record(reports, pending_again) is True
        assert read_ledger(reports)[0]["generated_at_utc"] == "2099-01-01T00:00:00+00:00"
        assert len(read_ledger(reports)) == 1

        _write(data_dir, "price_day_ahead", idx, price)
        score_ledger(data_dir, reports)
        assert append_record(reports, {**first, "pred_model": [0.0] * 24}) is False
        kept = read_ledger(reports)[0]
        assert kept["pred_model"] == first["pred_model"]
        assert kept["scored_at_utc"] is not None

    def test_partly_published_day_stays_pending(self, data, tmp_path):
        data_dir, idx, price = data
        reports = tmp_path / "reports"
        append_record(reports, make_prediction(data_dir, TARGET_DAY, FAST))
        # only half of the delivery day published — a half-scored day biases the MAE
        half = int((idx < day_start_utc(TARGET_DAY)).sum()) + 12
        _write(data_dir, "price_day_ahead", idx[:half], price[:half])
        assert score_ledger(data_dir, reports) == []


class TestSummary:
    RECORDS = [
        {
            "target_date": "2026-09-01",
            "scored_at_utc": "x",
            "feature_set": "pre_auction",
            "n_hours_scored": 24,
            "mae_model": 10.0,
            "mae_naive": 20.0,
            "mae_snaive7": 30.0,
        },
        {
            "target_date": "2026-09-02",
            "scored_at_utc": "x",
            "feature_set": "pre_auction",
            "n_hours_scored": 24,
            "mae_model": 30.0,
            "mae_naive": 20.0,
            "mae_snaive7": 10.0,
        },
        {"target_date": "2026-09-03", "scored_at_utc": None, "feature_set": "pre_auction"},
    ]

    def test_hand_computed_window(self):
        stats = window_stats(self.RECORDS[:2])
        assert stats == {
            "n_days": 2,
            "n_hours": 48,
            "mae_model": 20.0,
            "mae_naive": 20.0,
            "mae_snaive7": 20.0,
            "skill_vs_naive_pct": 0.0,
            "days_model_beat_naive": 1,
        }

    def test_summary_counts_pending_separately(self):
        summary = summarize_ledger(self.RECORDS)
        assert (summary["n_records"], summary["n_scored"], summary["n_pending"]) == (3, 2, 1)
        assert summary["first_target_date"] == "2026-09-01"
        assert summary["last_target_date"] == "2026-09-03"

    def test_empty_ledger_has_no_stats_instead_of_zeros(self):
        summary = summarize_ledger([])
        assert summary["n_records"] == 0
        assert summary["cumulative"] is None
        assert summary["last_7_days"] is None


class TestCli:
    def test_skip_is_not_a_failure(self, data, tmp_path):
        """SMARD not having published yet is a data fact, not a pipeline fault —
        exiting non-zero here would drown the real alerts."""
        data_dir, _, _ = data
        result = CliRunner().invoke(
            app,
            [
                "forecast-tomorrow",
                "--data-dir", str(data_dir),
                "--reports-dir", str(tmp_path / "reports"),
                "--target-date", str(TARGET_DAY + timedelta(days=3)),
            ],
        )
        assert result.exit_code == 0
        assert "SKIPPED" in result.output
        assert not (tmp_path / "reports").exists()

    def test_a_late_run_skips_instead_of_recording(self, data, tmp_path, monkeypatch):
        data_dir, _, _ = data
        late = gate_closure_utc(TARGET_DAY).to_pydatetime() + timedelta(minutes=40)
        monkeypatch.setattr(forward, "utc_now", lambda: late)
        result = CliRunner().invoke(
            app,
            [
                "forecast-tomorrow",
                "--data-dir", str(data_dir),
                "--reports-dir", str(tmp_path / "reports"),
                "--target-date", str(TARGET_DAY),
            ],
        )
        assert result.exit_code == 0
        assert "SKIPPED" in result.output and "closed" in result.output
        assert not (tmp_path / "reports").exists()

    def test_records_and_then_scores_through_the_cli(self, data, tmp_path):
        data_dir, idx, price = data
        reports = tmp_path / "reports"
        args = ["--data-dir", str(data_dir), "--reports-dir", str(reports)]
        runner = CliRunner()

        recorded = runner.invoke(
            app, ["forecast-tomorrow", *args, "--target-date", str(TARGET_DAY)]
        )
        assert recorded.exit_code == 0, recorded.output
        assert "recorded" in recorded.output

        pending = runner.invoke(app, ["score-ledger", *args])
        assert "0 scored, 1 pending" in pending.output

        _write(data_dir, "price_day_ahead", idx, price)
        done = runner.invoke(app, ["score-ledger", *args])
        assert done.exit_code == 0
        assert f"scored {TARGET_DAY}" in done.output
        assert "1 scored, 0 pending" in done.output
