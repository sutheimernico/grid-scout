import json

import pytest

from gridscout.readme_results import END, START, render_results, update_readme


@pytest.fixture
def reports(tmp_path):
    (tmp_path / "forecast_eval.json").write_text(
        json.dumps(
            {
                "generated_utc": "2026-10-28T07:00:00+00:00",
                "eval_period": {"start": "2025-10-26", "end": "2026-10-27"},
                "models": {
                    "naive_yesterday": {"mae": 30.0},
                    "seasonal_naive_7d": {"mae": 38.0},
                    "ridge_per_hour": {"mae": 22.5},
                    "lgbm_point": {"mae": 19.5},
                },
                "skill": {"lgbm_vs_naive_pct": 35.0},
                "pre_auction": {
                    "skill_vs_naive_pct": 17.0,
                    "models": {"lgbm_pre_auction": {"mae": 25.0}},
                },
                "quantiles": {"coverage_p10_p90": 0.62, "conformal": {"coverage_p10_p90": 0.75}},
            }
        )
    )
    (tmp_path / "battery_backtest.json").write_text(
        json.dumps(
            {
                "revenue_eur": {"model": 80000.0, "naive": 76000.0, "perfect": 85000.0},
                "capture_rate_model": 0.94,
                "model_edge_over_naive_eur": 4000.0,
            }
        )
    )
    return tmp_path


def test_table_carries_every_baseline_the_date_and_both_coverages(reports):
    text = render_results(reports)
    for expected in ("2026-10-28", "30.00", "38.00", "22.50", "19.50", "25.00", "62%", "75%"):
        assert expected in text
    assert "80,000" in text


def test_agent_lines_appear_only_when_reports_exist(reports):
    assert "holdout" not in render_results(reports)
    (reports / "agent_eval_holdout.json").write_text(
        json.dumps({"passed": 12, "n": 20, "pass_rate": 0.6})
    )
    assert "12/20 (60%)" in render_results(reports)


def test_update_replaces_only_the_marked_block(reports, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(f"intro\n{START}\nstale numbers\n{END}\noutro\n")
    assert update_readme(readme, reports) is True
    text = readme.read_text()
    assert text.startswith("intro\n") and text.endswith("\noutro\n")
    assert "stale numbers" not in text and "19.50" in text
    assert update_readme(readme, reports) is False  # idempotent


def test_missing_markers_fail_loudly(reports, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("no markers")
    with pytest.raises(ValueError, match="results:start"):
        update_readme(readme, reports)
