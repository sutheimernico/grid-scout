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
    report, predictions = evaluate(data_dir, EvalConfig(eval_days=eval_days, step_days=step_days))
    path = write_report(report, predictions, reports_dir)
    typer.echo(f"report written: {path}")
    typer.echo(report["finding"])


@app.command("battery-backtest")
def battery_backtest(
    reports_dir: Annotated[Path, typer.Option(help="Report directory")] = Path("reports"),
    power_mw: Annotated[float, typer.Option(help="Battery power")] = 1.0,
    capacity_mwh: Annotated[float, typer.Option(help="Battery capacity")] = 2.0,
    efficiency: Annotated[float, typer.Option(help="Round-trip efficiency")] = 0.86,
) -> None:
    """Battery arbitrage on walk-forward predictions (needs forecast-eval first)."""
    import json

    import pandas as pd

    from gridscout.battery.backtest import run_backtest
    from gridscout.battery.schedule import Battery

    predictions_path = reports_dir / "predictions.parquet"
    if not predictions_path.exists():
        raise typer.BadParameter(f"{predictions_path} missing — run forecast-eval first")
    predictions = pd.read_parquet(predictions_path)
    predictions["local_day"] = pd.to_datetime(predictions["local_day"]).dt.date

    actual = predictions.rename(columns={"target": "price"})
    battery = Battery(
        power_mw=power_mw, capacity_mwh=capacity_mwh, round_trip_efficiency=efficiency
    )
    result = run_backtest(
        actual[["local_day", "hour_local", "price"]],
        actual.assign(price=predictions["pred_point"])[["local_day", "hour_local", "price"]],
        battery,
    )
    out = {
        "battery": {
            "power_mw": power_mw,
            "capacity_mwh": capacity_mwh,
            "round_trip_efficiency": efficiency,
        },
        **result.summary,
    }
    (reports_dir / "battery_backtest.json").write_text(json.dumps(out, indent=2) + "\n")
    result.daily.assign(local_day=result.daily["local_day"].astype(str)).to_parquet(
        reports_dir / "battery_daily.parquet"
    )
    typer.echo(json.dumps(out, indent=2))


if __name__ == "__main__":
    app()
