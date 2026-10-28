"""gridscout CLI — pipeline entry points, designed to run locally and in CI."""

import logging
from datetime import UTC, datetime
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
        run = ingest_all(client, data_dir, names=list(series) if series else None)
    for r in run.results:
        marker = " ⚠" if r.report.warnings else ""
        typer.echo(f"{r.series}: {r.n_rows} rows ({r.weeks_fetched} weeks fetched){marker}")
    if run.failures:
        # A single series timing out is routine (SMARD is flaky) and must not turn
        # the pipeline red: the old Parquet stays in place and the health panel
        # shows the series going stale. Only a run where nothing could be fetched
        # is a real outage that should open the failure issue.
        total = len(run.results) + len(run.failures)
        for name, error in run.failures:
            typer.echo(f"::warning title=ingest {name}::{error}", err=True)
            typer.echo(f"{name}: FAILED - {error}", err=True)
        typer.echo(f"{len(run.failures)} of {total} series failed", err=True)
        if not run.results:
            raise typer.Exit(1)


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

    from gridscout.battery.backtest import frames_from_predictions, run_backtest
    from gridscout.battery.schedule import Battery

    actual, model = frames_from_predictions(pd.read_parquet(_predictions_path(reports_dir)))
    battery = Battery(
        power_mw=power_mw, capacity_mwh=capacity_mwh, round_trip_efficiency=efficiency
    )
    result = run_backtest(actual, model, battery)
    out = {
        # Health monitoring reads this back: an un-stamped report cannot be told
        # apart from a stale one (git does not preserve mtimes).
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
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


@app.command("battery-sensitivity")
def battery_sensitivity(
    reports_dir: Annotated[Path, typer.Option(help="Report directory")] = Path("reports"),
) -> None:
    """Re-run the battery backtest over efficiency x duration (needs forecast-eval first)."""
    import json

    import pandas as pd

    from gridscout.battery.backtest import frames_from_predictions
    from gridscout.battery.sensitivity import sweep

    actual, model = frames_from_predictions(pd.read_parquet(_predictions_path(reports_dir)))
    out = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        **sweep(actual, model),
    }
    (reports_dir / "battery_sensitivity.json").write_text(json.dumps(out, indent=2) + "\n")
    for cell in out["cells"]:
        typer.echo(
            f"eta {cell['round_trip_efficiency']:.2f} / {cell['duration_h']}h: "
            f"model {cell['revenue_eur_per_mw_year']['model']:,.0f} EUR/MW/yr, "
            f"capture {cell['capture_rate_model']:.1%}, "
            f"edge over naive {cell['model_edge_over_naive_eur_per_mw_year']:,.0f}"
        )


def _predictions_path(reports_dir: Path) -> Path:
    path = reports_dir / "predictions.parquet"
    if not path.exists():
        raise typer.BadParameter(f"{path} missing — run forecast-eval first")
    return path


@app.command("update-readme")
def update_readme_cmd(
    reports_dir: Annotated[Path, typer.Option(help="Report directory")] = Path("reports"),
    readme: Annotated[Path, typer.Option(help="README to update")] = Path("README.md"),
) -> None:
    """Regenerate the README results block from the report artifacts."""
    from gridscout.readme_results import update_readme

    changed = update_readme(readme, reports_dir)
    typer.echo("README results updated" if changed else "README results already current")


@app.command("agent-eval")
def agent_eval(
    data_dir: DataDirOpt = Path("data"),
    reports_dir: Annotated[Path, typer.Option(help="Report directory")] = Path("reports"),
    model: Annotated[str, typer.Option(help="Ollama model")] = "qwen2.5:7b",
    holdout: Annotated[bool, typer.Option(help="Also run the untuned holdout set")] = True,
) -> None:
    """Run the agent eval sets against a local Ollama model (requires ollama serve)."""
    from gridscout.agent.evaluation import build_holdout_set, run_eval
    from gridscout.agent.loop import GridAgent
    from gridscout.agent.tools import GridTools

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    tools = GridTools(data_dir=data_dir, reports_dir=reports_dir)
    agent = GridAgent(tools=tools, model=model)
    runs = [("development set", run_eval(agent, tools, reports_dir))]
    if holdout:
        runs.append(
            (
                "holdout set",
                run_eval(
                    agent, tools, reports_dir, build_holdout_set(tools), "agent_eval_holdout.json"
                ),
            )
        )
    for label, report in runs:
        typer.echo(
            f"{label}: pass rate {report['pass_rate']:.0%} ({report['passed']}/{report['n']}) — "
            + ", ".join(f"{k}: {v['passed']}/{v['n']}" for k, v in report["by_type"].items())
        )


@app.command("forecast-tomorrow")
def forecast_tomorrow(
    data_dir: DataDirOpt = Path("data"),
    reports_dir: Annotated[Path, typer.Option(help="Report directory")] = Path("reports"),
    target_date: Annotated[
        str | None, typer.Option(help="Delivery day (YYYY-MM-DD); default tomorrow")
    ] = None,
) -> None:
    """Record one pre-auction forecast for the next delivery day in the forward ledger.

    Skips (exit 0) when SMARD has not published enough yet, when the day's
    auction has already closed, or when its prices are already out — that is a
    timing fact, not a pipeline failure, and it must not drown the real alerts.
    """
    from datetime import date as date_type

    from gridscout.forecast.forward import (
        NotForecastable,
        append_record,
        make_prediction,
        next_delivery_day,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    day = date_type.fromisoformat(target_date) if target_date else next_delivery_day()
    try:
        record = make_prediction(data_dir, day)
    except NotForecastable as exc:
        typer.echo(f"SKIPPED {day}: {exc}")
        return
    written = append_record(reports_dir, record)
    verb = "recorded" if written else "kept existing scored record for"
    typer.echo(
        f"{verb} {day}: {len(record['pred_model'])}h, model {record['model_version']}, "
        f"features {record['feature_set']}, trained on {record['train_rows']} rows"
    )


@app.command("score-ledger")
def score_ledger_command(
    data_dir: DataDirOpt = Path("data"),
    reports_dir: Annotated[Path, typer.Option(help="Report directory")] = Path("reports"),
) -> None:
    """Score forward-ledger entries whose delivery day has cleared."""
    from gridscout.forecast.forward import read_ledger, score_ledger, summarize_ledger

    scored = score_ledger(data_dir, reports_dir)
    summary = summarize_ledger(read_ledger(reports_dir))
    for record in scored:
        typer.echo(
            f"scored {record['target_date']}: MAE model {record['mae_model']:.2f} vs "
            f"naive {record['mae_naive']:.2f} vs seasonal-naive {record['mae_snaive7']:.2f}"
        )
    typer.echo(
        f"ledger: {summary['n_scored']} scored, {summary['n_pending']} pending "
        f"({len(scored)} newly scored)"
    )


@app.command("export-site")
def export_site(
    data_dir: DataDirOpt = Path("data"),
    reports_dir: Annotated[Path, typer.Option(help="Report directory")] = Path("reports"),
    out_dir: Annotated[Path, typer.Option(help="Site data directory")] = Path("site/public/data"),
) -> None:
    """Write dashboard JSON artifacts (skips exports whose inputs are missing)."""
    from gridscout.export import export_site_data

    written = export_site_data(data_dir, reports_dir, out_dir)
    typer.echo(f"written: {', '.join(written) or '(nothing — no inputs found)'}")


if __name__ == "__main__":
    app()
