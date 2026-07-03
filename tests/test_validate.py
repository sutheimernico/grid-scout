import pandas as pd

from gridscout.smard.filters import SERIES
from gridscout.smard.validate import HOUR_MS, validate_series
from tests.conftest import WEEK1


def frame(values, start=WEEK1, step=HOUR_MS):
    return pd.DataFrame(
        {"timestamp_ms": [start + i * step for i in range(len(values))], "value": values}
    )


PRICE = SERIES["price_day_ahead"]


def test_valid_series_passes():
    report = validate_series(PRICE, frame([100.0, -50.5, 300.0]))
    assert report.ok
    assert report.n_rows == 3


def test_empty_series_fails():
    report = validate_series(PRICE, frame([]))
    assert not report.ok


def test_duplicate_timestamp_fails():
    df = pd.concat([frame([1.0, 2.0]), frame([2.5])], ignore_index=True)
    report = validate_series(PRICE, df.sort_values("timestamp_ms").reset_index(drop=True))
    assert any("increasing" in e for e in report.errors)


def test_gap_fails():
    df = frame([1.0, 2.0, 3.0], step=2 * HOUR_MS)
    report = validate_series(PRICE, df)
    assert any("gaps" in e for e in report.errors)


def test_unit_error_caught():
    report = validate_series(PRICE, frame([100.0, 99_999.0]))
    assert any("outside" in e for e in report.errors)


def test_negative_price_is_fine_but_negative_generation_is_not():
    assert validate_series(PRICE, frame([-200.0])).ok
    report = validate_series(SERIES["gen_solar"], frame([-200.0]))
    assert not report.ok


def test_high_null_fraction_warns_but_passes():
    values = [1.0] * 10 + [None] * 10
    report = validate_series(PRICE, frame(values))
    assert report.ok
    assert report.warnings
