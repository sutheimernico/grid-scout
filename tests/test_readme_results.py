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
                    "n": 8700,
                    "skill_vs_naive_pct": 17.0,
                    "models": {
                        "naive_yesterday": {"mae": 30.1},
                        "seasonal_naive_7d": {"mae": 38.1},
                        "ridge_pre_auction": {"mae": 26.1},
                        "lgbm_pre_auction": {"mae": 25.0},
                        "lgbm_gate_closure": {"mae": 19.6},
                    },
                },
                "quantiles": {"coverage_p10_p90": 0.62, "conformal": {"coverage_p10_p90": 0.75}},
            }
        )
    )
    (tmp_path / "battery_backtest.json").write_text(
        json.dumps(
            {
                "n_days": 363,
                "revenue_eur_per_mw_year": {"model": 78000.0, "naive": 76000.0, "perfect": 85000.0},
                "capture_rate_model": 0.91,
                "model_edge_over_naive_eur_per_mw_year": 2000.0,
                "full_model": {
                    "model_edge_over_naive_eur_per_mw_year": 4400.0,
                    "capture_rate_model": 0.94,
                },
            }
        )
    )
    (tmp_path / "battery_sensitivity.json").write_text(
        json.dumps(
            {
                "cells": [
                    {"model_edge_over_naive_eur_per_mw_year": 4400.0},
                    {"model_edge_over_naive_eur_per_mw_year": 8600.0},
                ]
            }
        )
    )
    return tmp_path


def test_table_uses_one_sample_leads_with_pre_auction_and_annualises(reports):
    text = render_results(reports)
    for expected in ("2026-10-28", "30.10", "38.10", "26.10", "25.00", "19.60", "62%", "75%"):
        assert expected in text
    assert "30.00" not in text and "22.50" not in text  # no numbers from the other sample
    assert text.index("25.00") < text.index("19.60")  # honest pre-auction model first
    assert "+17.0% vs naive" in text and "+34.9% vs naive" in text
    assert "annualised from 363 days" in text
    assert "+2,000 €/MW/yr" in text and "+4,400 €/MW/yr" in text
    assert "between 4,400 and 8,600" in text


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
    assert "stale numbers" not in text and "19.60" in text
    assert update_readme(readme, reports) is False  # idempotent


def test_missing_markers_fail_loudly(reports, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("no markers")
    with pytest.raises(ValueError, match="results:start"):
        update_readme(readme, reports)
