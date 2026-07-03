"""Incremental ingestion: SMARD weekly JSON -> one Parquet per series.

Idempotent: closed weeks come from the on-disk cache or existing Parquet; only
weeks not yet fully present (plus the trailing weeks, which SMARD keeps
updating) are fetched from the API.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from gridscout.smard.client import SmardClient
from gridscout.smard.filters import DEEP_HISTORY_NAMES, SERIES, SeriesSpec
from gridscout.smard.validate import ValidationReport, validate_series

logger = logging.getLogger(__name__)

# Weeks whose data SMARD may still revise and which are therefore always refetched.
TRAILING_WEEKS_REFRESHED = 2

DEEP_HISTORY_START = datetime(2021, 1, 1, tzinfo=UTC)
SHALLOW_HISTORY_START = datetime(2024, 1, 1, tzinfo=UTC)


@dataclass
class IngestResult:
    series: str
    weeks_fetched: int
    n_rows: int
    report: ValidationReport


def series_path(data_dir: Path, name: str) -> Path:
    return data_dir / f"{name}.parquet"


def ingest_series(
    client: SmardClient, spec: SeriesSpec, data_dir: Path, start: datetime
) -> IngestResult:
    index = client.week_index(spec.filter_id)
    start_ms = int(start.timestamp() * 1000)
    wanted = [ts for ts in index if ts >= start_ms]
    has_trailing = len(wanted) >= TRAILING_WEEKS_REFRESHED
    refresh_from = wanted[-TRAILING_WEEKS_REFRESHED] if has_trailing else 0

    path = series_path(data_dir, spec.name)
    existing = pd.read_parquet(path) if path.exists() else None
    have_ms = set() if existing is None else set(existing["timestamp_ms"])

    frames = []
    weeks_fetched = 0
    for week_ts in wanted:
        refresh = week_ts >= refresh_from
        if not refresh and _week_complete(have_ms, week_ts):
            continue
        points = client.week_series(spec.filter_id, week_ts, refresh=refresh)
        weeks_fetched += 1
        frames.append(
            pd.DataFrame({"timestamp_ms": [t for t, _ in points], "value": [v for _, v in points]})
        )

    if frames:
        new = pd.concat(frames, ignore_index=True)
        merged = new if existing is None else pd.concat([existing, new], ignore_index=True)
        # Newly fetched rows win over previously stored ones (SMARD revises data).
        merged = (
            merged.drop_duplicates("timestamp_ms", keep="last")
            .sort_values("timestamp_ms")
            .reset_index(drop=True)
        )
    else:
        merged = existing if existing is not None else pd.DataFrame(
            {"timestamp_ms": pd.Series(dtype="int64"), "value": pd.Series(dtype="float64")}
        )

    merged = merged.astype({"timestamp_ms": "int64", "value": "float64"})
    # Trailing hours SMARD has not published yet arrive as nulls — drop them so the
    # stored series ends at the last real observation.
    last_real = merged["value"].last_valid_index()
    if last_real is not None:
        merged = merged.loc[:last_real].reset_index(drop=True)

    report = validate_series(spec, merged)
    if not report.ok:
        raise ValueError(f"validation failed for {spec.name}: {report.errors}")

    data_dir.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(path, index=False)
    logger.info("%s: %d rows (%d weeks fetched)", spec.name, len(merged), weeks_fetched)
    return IngestResult(spec.name, weeks_fetched, len(merged), report)


def ingest_all(
    client: SmardClient, data_dir: Path, names: list[str] | None = None
) -> list[IngestResult]:
    results = []
    for name in names or list(SERIES):
        spec = SERIES[name]
        start = DEEP_HISTORY_START if name in DEEP_HISTORY_NAMES else SHALLOW_HISTORY_START
        results.append(ingest_series(client, spec, data_dir, start))
    return results


def _week_complete(have_ms: set[int], week_ts: int) -> bool:
    week_hours = {week_ts + i * 3_600_000 for i in range(168)}
    return week_hours <= have_ms
