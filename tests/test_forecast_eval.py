import numpy as np
import pytest

from gridscout.forecast.metrics import coverage, mae, pinball, rmse, summarize
from gridscout.forecast.models import LightGBMPrice, NaiveYesterday, SeasonalNaiveWeek
from gridscout.forecast.walkforward import make_folds, run_walkforward
from tests.test_features import build_matrix, synthetic_raw


class TestMetrics:
    def test_mae_rmse_hand_computed(self):
        y, p = np.array([1.0, 2.0, 3.0]), np.array([2.0, 2.0, 5.0])
        assert mae(y, p) == pytest.approx(1.0)
        assert rmse(y, p) == pytest.approx(np.sqrt(5 / 3))

    def test_pinball_asymmetry(self):
        y, p = np.array([10.0]), np.array([0.0])  # under-prediction by 10
        assert pinball(y, p, 0.9) == pytest.approx(9.0)
        assert pinball(y, p, 0.1) == pytest.approx(1.0)

    def test_coverage(self):
        y = np.array([1.0, 5.0, 9.0])
        assert coverage(y, np.zeros(3), np.full(3, 6.0)) == pytest.approx(2 / 3)

    def test_summarize_by_hour(self):
        result = summarize(
            np.array([1.0, 1.0]), np.array([2.0, 4.0]), hours=np.array([0, 1])
        )
        assert result["mae"] == pytest.approx(2.0)
        assert result["mae_by_hour"] == {0: 1.0, 1: 3.0}


class TestWalkForward:
    def test_folds_expand_and_never_overlap(self):
        days = list(range(20))  # any orderable works
        folds = make_folds(days, min_train_days=10, step_days=3)
        assert [len(f.train_days) for f in folds] == [10, 13, 16, 19]
        for fold in folds:
            assert max(fold.train_days) < min(fold.test_days)
        covered = [d for f in folds for d in f.test_days]
        assert covered == days[10:]

    def test_naive_prediction_equals_lag_column(self):
        matrix = build_matrix(synthetic_raw(days=30))
        days = sorted(matrix["local_day"].unique())
        folds = make_folds(days, min_train_days=14)
        result = run_walkforward(matrix, NaiveYesterday(), folds)
        expected = matrix.loc[result.index, "price_lag_1d"]
        assert np.allclose(result["prediction"], expected)

    def test_results_cover_only_test_days(self):
        matrix = build_matrix(synthetic_raw(days=30))
        days = sorted(matrix["local_day"].unique())
        folds = make_folds(days, min_train_days=14)
        result = run_walkforward(matrix, SeasonalNaiveWeek(), folds)
        assert set(result["local_day"]) == set(days[14:])


class TestLightGBM:
    def test_learns_linear_signal_and_is_deterministic(self):
        matrix = build_matrix(synthetic_raw(days=60))
        # plant a learnable signal: target = f(forecast_solar)
        matrix["target"] = matrix["forecast_solar"] * 0.002 + 10

        days = sorted(matrix["local_day"].unique())
        folds = make_folds(days, min_train_days=35, step_days=7)
        model = LightGBMPrice(n_estimators=80)
        first = run_walkforward(matrix, model, folds)
        second = run_walkforward(matrix, LightGBMPrice(n_estimators=80), folds)

        assert mae(first["target"].to_numpy(), first["prediction"].to_numpy()) < 5.0
        assert np.array_equal(first["prediction"], second["prediction"])

    def test_quantile_models_order(self):
        matrix = build_matrix(synthetic_raw(days=60))
        days = sorted(matrix["local_day"].unique())
        folds = make_folds(days, min_train_days=45, step_days=7)
        q10 = run_walkforward(matrix, LightGBMPrice(quantile=0.1, n_estimators=60), folds)
        q90 = run_walkforward(matrix, LightGBMPrice(quantile=0.9, n_estimators=60), folds)
        # quantile crossing can happen pointwise; on average the order must hold
        assert q10["prediction"].mean() < q90["prediction"].mean()
