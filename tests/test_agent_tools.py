import json

import numpy as np
import pytest

from gridscout.agent.tools import GridTools, ToolError
from tests.conftest import HOUR_MS
from tests.test_export import write_series

# 2024-03-01 00:00 Europe/Berlin == 2024-02-29 23:00 UTC == 1709247600 s
START_MS = 1709247600000


@pytest.fixture
def tools(tmp_path):
    data = tmp_path / "data"
    n = 96  # 4 days: Mar 1-4, 2024
    rng = np.random.default_rng(11)
    prices = rng.normal(80, 30, n)
    prices[30] = -12.0  # a negative hour on day 2
    write_series(data, "price_day_ahead", prices, start_ms=START_MS)
    write_series(data, "load", rng.uniform(45_000, 65_000, n), start_ms=START_MS)
    for name in ["gen_solar", "gen_wind_onshore", "gen_wind_offshore", "gen_gas", "gen_lignite"]:
        write_series(data, name, rng.uniform(100, 20_000, n), start_ms=START_MS)

    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "forecast_eval.json").write_text(
        json.dumps({"models": {"lgbm_point": {"mae": 15.25}}, "skill": {"lgbm_vs_naive_pct": 44.0}})
    )
    return GridTools(data_dir=data, reports_dir=reports)


class TestPriceDay:
    def test_full_day(self, tools):
        result = tools.get_price_day("2024-03-02")
        assert len(result["hourly"]) == 24
        assert result["negative_hours"] == 1
        assert result["min"]["value"] == -12.0
        assert result["min"]["hour"] == 6  # index 30 = day2 hour 6

    def test_unknown_day_names_available_range(self, tools):
        with pytest.raises(ToolError, match="2024-03-01 to 2024-03-04"):
            tools.get_price_day("2030-01-01")

    def test_bad_date_format(self, tools):
        with pytest.raises(ToolError, match="not an ISO date"):
            tools.get_price_day("gestern")


class TestRangeSummary:
    def test_range(self, tools):
        result = tools.get_price_range_summary("2024-03-01", "2024-03-04")
        assert result["n_hours"] == 96
        assert result["negative_hours"] == 1

    def test_reversed_range_rejected(self, tools):
        with pytest.raises(ToolError, match="before start_day"):
            tools.get_price_range_summary("2024-03-04", "2024-03-01")


class TestGenerationAndContext:
    def test_mix_shares_sum(self, tools):
        result = tools.get_generation_mix_day("2024-03-02")
        assert result["total"] == pytest.approx(sum(result["by_source"].values()), rel=0.01)
        assert 0 <= result["renewables_share"] <= 1

    def test_context_has_correlation_and_extremes(self, tools):
        result = tools.explain_price_context("2024-03-02")
        assert -1 <= result["correlation_price_vs_residual_load"] <= 1
        assert len(result["cheapest_hours"]) == 3
        assert result["cheapest_hours"][0]["price"] == -12.0


class TestReports:
    def test_eval_passthrough(self, tools):
        assert tools.get_forecast_evaluation()["skill"]["lgbm_vs_naive_pct"] == 44.0

    def test_missing_battery_report(self, tools):
        with pytest.raises(ToolError, match="not been produced"):
            tools.get_battery_results()


def test_coverage_lists_missing(tools):
    coverage = tools.get_data_coverage()
    assert coverage["series"]["price_day_ahead"]["available"]
    assert not coverage["series"]["forecast_solar"]["available"]


def test_hour_ms_constant_matches():
    assert HOUR_MS == 3_600_000
