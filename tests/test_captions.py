import numpy as np
import pandas as pd
import pytest

from gridscout.analysis.captions import align, caption, describe, window_facts

TZ = "Europe/Berlin"


def day_frame(prices, solar=None, wind=None, load=None, day="2026-09-19"):
    idx = pd.date_range(f"{day} 00:00", periods=len(prices), freq="h", tz=TZ)
    n = len(prices)
    solar = np.zeros(n) if solar is None else np.asarray(solar, dtype=float)
    wind = np.full(n, 5_000.0) if wind is None else np.asarray(wind, dtype=float)
    load = np.full(n, 50_000.0) if load is None else np.asarray(load, dtype=float)
    return align(
        pd.Series(np.asarray(prices, dtype=float), index=idx),
        pd.Series(load, index=idx),
        pd.Series(solar, index=idx),
        pd.Series(wind, index=idx),
    )


class TestFacts:
    def test_hand_computed_extremes_and_residual_load(self):
        prices = [10.0] * 24
        prices[13] = -5.0
        prices[20] = 200.0
        solar = [0.0] * 24
        solar[13] = 30_000.0
        facts = window_facts(day_frame(prices, solar=solar))

        assert facts["n_hours"] == 24
        assert facts["min_price"] == -5.0
        assert facts["max_price"] == 200.0
        assert facts["spread"] == 205.0
        assert facts["negative_hours"] == 1
        assert facts["solar_peak_mwh"] == 30_000
        assert facts["wind_mean_mwh"] == 5_000
        assert facts["cheapest_hours"][0] == {
            "hour": 13,
            "price": -5.0,
            "residual_load_mwh": 15_000,  # 50k load - 30k solar - 5k wind
        }
        assert facts["priciest_hours"][0]["hour"] == 20

    def test_constant_price_gives_no_correlation_instead_of_nan(self):
        facts = window_facts(day_frame([42.0] * 24))
        assert facts["correlation_price_vs_residual_load"] is None

    def test_empty_and_malformed_windows_raise(self):
        with pytest.raises(ValueError, match="no overlapping hours"):
            window_facts(day_frame([]))
        with pytest.raises(ValueError, match="missing columns"):
            window_facts(pd.DataFrame({"price": [1.0]}))


class TestCaption:
    def test_normal_day_names_both_extremes_and_the_relationship(self):
        prices = [40.0 + h for h in range(24)]
        load = [45_000.0 + 400 * h for h in range(24)]  # price follows residual load
        text = caption(window_facts(day_frame(prices, load=load)))
        assert "Cheapest hour 00:00 at 40.00 EUR/MWh" in text
        assert "most expensive 23:00 at 63.00 EUR/MWh" in text
        assert "tracks residual load" in text
        assert "cleared below zero" not in text
        assert "scarcity hour" not in text

    def test_negative_price_day_says_so_and_counts_the_hours(self):
        prices = [10.0] * 24
        for h in (11, 12, 13):
            prices[h] = -20.0
        text = caption(window_facts(day_frame(prices, solar=[25_000.0] * 24)))
        assert "3 hours cleared below zero" in text
        assert "renewables covered more than the grid could absorb" in text

    def test_spike_day_is_called_a_spike_only_when_both_bars_are_cleared(self):
        spike = [20.0] * 24
        spike[19] = 450.0
        assert "scarcity hour" in caption(window_facts(day_frame(spike)))

        # expensive but flat: high absolute level, no relative outlier
        flat_expensive = [250.0] * 24
        assert "scarcity hour" not in caption(window_facts(day_frame(flat_expensive)))

        # relative outlier on a cheap day: 5 EUR mean, 30 EUR peak is not scarcity
        cheap = [5.0] * 24
        cheap[19] = 30.0
        assert "scarcity hour" not in caption(window_facts(day_frame(cheap)))

    def test_single_negative_hour_is_singular(self):
        prices = [10.0] * 24
        prices[13] = -1.0
        assert "1 hour cleared below zero" in caption(window_facts(day_frame(prices)))


def test_describe_is_json_clean():
    payload = describe(day_frame([10.0 + h for h in range(24)]))
    assert "caption" in payload
    assert not [k for k in payload if k.startswith("_")]
    import json

    json.dumps(payload, allow_nan=False)


def test_agent_and_site_share_the_same_numbers(tmp_path):
    """The agent tool and the dashboard caption must not drift apart."""
    from gridscout.agent.tools import GridTools

    idx = pd.date_range("2026-09-19 00:00", periods=24, freq="h", tz=TZ).tz_convert("UTC")
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    rng = np.random.default_rng(5)
    series = {
        "price_day_ahead": rng.normal(60, 30, 24),
        "load": rng.uniform(40_000, 60_000, 24),
        "gen_solar": rng.uniform(0, 25_000, 24),
        "gen_wind_onshore": rng.uniform(0, 15_000, 24),
        "gen_wind_offshore": rng.uniform(0, 5_000, 24),
    }
    for name, values in series.items():
        pd.DataFrame(
            {"timestamp_ms": (idx - epoch) // pd.Timedelta("1ms"), "value": values}
        ).to_parquet(tmp_path / f"{name}.parquet", index=False)

    context = GridTools(data_dir=tmp_path).explain_price_context("2026-09-19")
    frame = align(
        pd.Series(series["price_day_ahead"], index=idx.tz_convert(TZ)),
        pd.Series(series["load"], index=idx.tz_convert(TZ)),
        pd.Series(series["gen_solar"], index=idx.tz_convert(TZ)),
        pd.Series(
            series["gen_wind_onshore"] + series["gen_wind_offshore"], index=idx.tz_convert(TZ)
        ),
    )
    assert context["summary"] == describe(frame)["caption"]
    assert context["cheapest_hours"] == describe(frame)["cheapest_hours"]
