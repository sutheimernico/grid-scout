"""Thin HTTP client for the SMARD chart_data API.

API shape (verified 2026-07-03):
- index:  /app/chart_data/{filter}/DE/index_hour.json
          -> {"timestamps": [<ms epoch of week start, Europe/Berlin Monday 00:00>]}
- week:   /app/chart_data/{filter}/DE/{filter}_DE_hour_{ts}.json
          -> {"meta_data": {...}, "series": [[ms_epoch, value|null], ...]}

Closed weeks never change, so they are cached on disk forever; only the current
(and on request, previous) week is refetched.
"""

import json
import logging
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.smard.de/app/chart_data"
REGION = "DE"
RESOLUTION = "hour"

WeekSeries = list[tuple[int, float | None]]


class SmardClient:
    def __init__(
        self,
        cache_dir: Path,
        transport: httpx.BaseTransport | None = None,
        request_delay_s: float = 0.05,
        max_retries: int = 4,
    ):
        self.cache_dir = cache_dir
        self.request_delay_s = request_delay_s
        self.max_retries = max_retries
        self._http = httpx.Client(timeout=30, transport=transport)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "SmardClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def week_index(self, filter_id: int) -> list[int]:
        """Week-start timestamps (ms epoch) available for a filter, ascending."""
        payload = self._get_json(f"{BASE_URL}/{filter_id}/{REGION}/index_{RESOLUTION}.json")
        return sorted(payload["timestamps"])

    def week_series(self, filter_id: int, week_ts: int, *, refresh: bool = False) -> WeekSeries:
        """Hourly (timestamp_ms, value) points for one week, from cache or API."""
        cache_file = self.cache_dir / str(filter_id) / f"{week_ts}.json"
        if cache_file.exists() and not refresh:
            payload = json.loads(cache_file.read_text())
        else:
            name = f"{filter_id}_{REGION}_{RESOLUTION}_{week_ts}.json"
            url = f"{BASE_URL}/{filter_id}/{REGION}/{name}"
            payload = self._get_json(url)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(payload))
        return [(int(t), v) for t, v in payload["series"]]

    def _get_json(self, url: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                if self.request_delay_s:
                    time.sleep(self.request_delay_s)
                response = self._http.get(url)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_error = exc
                backoff = 2**attempt
                logger.warning("GET %s failed (%s), retry in %ss", url, exc, backoff)
                time.sleep(backoff)
        raise RuntimeError(
            f"SMARD request failed after {self.max_retries} retries: {url}"
        ) from last_error
