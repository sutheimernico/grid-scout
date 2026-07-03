"""Structural and plausibility validation for ingested series."""

from dataclasses import dataclass, field

import pandas as pd

from gridscout.smard.filters import Kind, SeriesSpec

HOUR_MS = 3_600_000

# Plausibility bounds per series kind. Day-ahead prices are genuinely negative at
# times (renewables oversupply) and spiked past 800 EUR/MWh in 2022 — bounds are
# wide on purpose; they catch unit errors, not market extremes.
VALUE_BOUNDS: dict[Kind, tuple[float, float]] = {
    Kind.PRICE: (-1_000.0, 10_000.0),
    Kind.LOAD: (-100_000.0, 150_000.0),  # residual load can go negative
    Kind.GENERATION: (0.0, 150_000.0),
    Kind.FORECAST: (0.0, 150_000.0),
}


@dataclass
class ValidationReport:
    series: str
    n_rows: int = 0
    null_fraction: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_series(spec: SeriesSpec, df: pd.DataFrame) -> ValidationReport:
    """df: columns [timestamp_ms:int64, value:float64 (nullable)], ascending."""
    report = ValidationReport(series=spec.name, n_rows=len(df))
    if df.empty:
        report.errors.append("series is empty")
        return report

    ts = df["timestamp_ms"]
    if not ts.is_monotonic_increasing or ts.duplicated().any():
        report.errors.append("timestamps not strictly increasing")
    gaps = ts.diff().dropna()
    if not (gaps == HOUR_MS).all():
        # DST transitions do NOT create gaps (epochs are absolute); any gap is real.
        bad = int((gaps != HOUR_MS).sum())
        report.errors.append(f"{bad} non-hourly timestamp gaps")

    values = df["value"]
    report.null_fraction = float(values.isna().mean())
    if report.null_fraction > 0.05:
        report.warnings.append(f"high null fraction: {report.null_fraction:.1%}")

    low, high = VALUE_BOUNDS[spec.kind]
    out_of_bounds = values.dropna()
    out_of_bounds = out_of_bounds[(out_of_bounds < low) | (out_of_bounds > high)]
    if len(out_of_bounds):
        report.errors.append(
            f"{len(out_of_bounds)} values outside [{low}, {high}], "
            f"e.g. {out_of_bounds.iloc[0]}"
        )
    return report
