import httpx
import pytest

from gridscout.smard.client import SmardClient
from tests.conftest import WEEK1, WEEK2, make_week


def make_client(fake_smard, tmp_path, **kwargs) -> SmardClient:
    return SmardClient(
        cache_dir=tmp_path / "cache",
        transport=fake_smard.transport,
        request_delay_s=0,
        **kwargs,
    )


def test_week_index_sorted(fake_smard, tmp_path):
    fake_smard.set_week(4169, WEEK2, make_week(WEEK2, 100))
    fake_smard.set_week(4169, WEEK1, make_week(WEEK1, 50))
    with make_client(fake_smard, tmp_path) as client:
        assert client.week_index(4169) == [WEEK1, WEEK2]


def test_week_series_parses_points(fake_smard, tmp_path):
    fake_smard.set_week(4169, WEEK1, make_week(WEEK1, 50, n_null_tail=3))
    with make_client(fake_smard, tmp_path) as client:
        points = client.week_series(4169, WEEK1)
    assert len(points) == 168
    assert points[0] == (WEEK1, 50.0)
    assert points[-1][1] is None


def test_closed_week_served_from_cache(fake_smard, tmp_path):
    fake_smard.set_week(4169, WEEK1, make_week(WEEK1, 50))
    with make_client(fake_smard, tmp_path) as client:
        client.week_series(4169, WEEK1)
        n_requests = len(fake_smard.requests)
        client.week_series(4169, WEEK1)
    assert len(fake_smard.requests) == n_requests


def test_refresh_bypasses_cache(fake_smard, tmp_path):
    fake_smard.set_week(4169, WEEK1, make_week(WEEK1, 50))
    with make_client(fake_smard, tmp_path) as client:
        client.week_series(4169, WEEK1)
        fake_smard.set_week(4169, WEEK1, make_week(WEEK1, 99))
        points = client.week_series(4169, WEEK1, refresh=True)
    assert points[0][1] == 99.0


def test_retries_then_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("gridscout.smard.client.time.sleep", lambda _: None)
    calls = []

    def always_500(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(500)

    client = SmardClient(
        cache_dir=tmp_path,
        transport=httpx.MockTransport(always_500),
        request_delay_s=0,
        max_retries=3,
    )
    with pytest.raises(RuntimeError, match="after 3 retries"):
        client.week_index(4169)
    assert len(calls) == 3
