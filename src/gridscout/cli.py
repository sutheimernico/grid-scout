"""gridscout CLI — pipeline entry points, designed to run locally and in CI."""

import logging
from pathlib import Path
from typing import Annotated

import typer

from gridscout.smard.client import SmardClient
from gridscout.smard.filters import SERIES
from gridscout.smard.ingest import ingest_all

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
    """grid-scout pipeline commands."""

SeriesOpt = Annotated[
    list[str] | None, typer.Option("--series", "-s", help="Subset of series names")
]
DataDirOpt = Annotated[Path, typer.Option(help="Parquet output directory")]
CacheDirOpt = Annotated[Path, typer.Option(help="Raw weekly JSON cache")]


@app.command()
def ingest(
    series: SeriesOpt = None,
    data_dir: DataDirOpt = Path("data"),
    cache_dir: CacheDirOpt = Path(".cache/smard"),
) -> None:
    """Fetch SMARD series into partitioned Parquet (incremental, idempotent)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    unknown = set(series or []) - set(SERIES)
    if unknown:
        raise typer.BadParameter(f"unknown series: {sorted(unknown)}; known: {sorted(SERIES)}")
    with SmardClient(cache_dir=cache_dir) as client:
        results = ingest_all(client, data_dir, names=list(series) if series else None)
    for r in results:
        marker = " ⚠" if r.report.warnings else ""
        typer.echo(f"{r.series}: {r.n_rows} rows ({r.weeks_fetched} weeks fetched){marker}")


@app.command("forecast-eval")
def forecast_eval(
    data_dir: DataDirOpt = Path("data"),
    reports_dir: Annotated[Path, typer.Option(help="Report output directory")] = Path("reports"),
    eval_days: Annotated[int, typer.Option(help="Days in the eval window")] = 365,
    step_days: Annotated[int, typer.Option(help="Refit cadence in days")] = 7,
) -> None:
    """Walk-forward evaluation: baselines vs LightGBM, honest report."""
    from gridscout.forecast.evaluate import EvalConfig, evaluate, write_report

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    report = evaluate(data_dir, EvalConfig(eval_days=eval_days, step_days=step_days))
    path = write_report(report, reports_dir)
    typer.echo(f"report written: {path}")
    typer.echo(report["finding"])


if __name__ == "__main__":
    app()
