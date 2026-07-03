import json

import httpx
import pytest

HOUR_MS = 3_600_000
WEEK_MS = 168 * HOUR_MS
# Monday 2024-01-01 00:00 Europe/Berlin == 2023-12-31 23:00 UTC
WEEK1 = 1704063600000
WEEK2 = WEEK1 + WEEK_MS
WEEK3 = WEEK2 + WEEK_MS


def make_week(week_ts: int, base: float, n_null_tail: int = 0) -> list[list]:
    points = []
    for i in range(168):
        value = None if i >= 168 - n_null_tail else base + i * 0.5
        points.append([week_ts + i * HOUR_MS, value])
    return points


class FakeSmard:
    """In-memory SMARD API behind an httpx.MockTransport, counting requests."""

    def __init__(self):
        self.weeks: dict[int, dict[int, list[list]]] = {}  # filter_id -> {week_ts: series}
        self.requests: list[str] = []

    def set_week(self, filter_id: int, week_ts: int, series: list[list]) -> None:
        self.weeks.setdefault(filter_id, {})[week_ts] = series

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.path)
        parts = request.url.path.split("/")
        filter_id = int(parts[3])
        if parts[-1].startswith("index_"):
            return httpx.Response(200, json={"timestamps": sorted(self.weeks[filter_id])})
        week_ts = int(parts[-1].split("_")[-1].removesuffix(".json"))
        series = self.weeks[filter_id].get(week_ts)
        if series is None:
            return httpx.Response(404)
        return httpx.Response(200, json={"meta_data": {"version": 1}, "series": series})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def fake_smard() -> FakeSmard:
    return FakeSmard()


def read_cache(cache_dir, filter_id: int, week_ts: int):
    return json.loads((cache_dir / str(filter_id) / f"{week_ts}.json").read_text())
