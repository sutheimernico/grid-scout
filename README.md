# grid-scout

Self-operating German electricity-market intelligence system — built on a 0-€,
GitHub-only stack.

> **Status: under construction.** This README grows with the project; see
> [PROJECT.md](PROJECT.md) for the vision and [PLAN.md](PLAN.md) for build progress.

- **Data:** [SMARD](https://www.smard.de) (Bundesnetzagentur, CC BY 4.0) — day-ahead
  prices, grid load, generation mix, hourly.
- **Pipeline:** GitHub Actions on a schedule — ingest, forecast, backtest, publish.
- **Forecast:** LightGBM day-ahead price forecast, walk-forward validated against
  honest baselines, leakage-guarded.
- **Backtest:** battery-storage arbitrage on forecast vs. perfect-foresight prices.
- **Dashboard:** static site on GitHub Pages, fed by pipeline artifacts.
- **Agent:** local-only (Ollama) with an MCP server and a measured eval harness.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```
