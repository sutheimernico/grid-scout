"""gridscout CLI — pipeline entry points, designed to run locally and in CI."""

import logging
from pathlib import Path
from typing import Annotated

import typer

from gridscout.smard.client import SmardClient
from gridscout.smard.filters import SERIES
from gridscout.smard.ingest import ingest_all

app = typer.Typer(no_args_is_help=True, add_completion=False)

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


if __name__ == "__main__":
    app()
