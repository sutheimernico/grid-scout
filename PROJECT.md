# grid-scout

Self-operating German electricity-market intelligence system. A public GitHub repo
that ingests real market data on a schedule, forecasts day-ahead prices with honest
validation, backtests a battery-storage arbitrage strategy on those forecasts, and
publishes everything to a live static dashboard — plus a local LLM agent with an
MCP server and a real evaluation harness.

## Vision

A hiring manager opens the live dashboard and sees a system that runs itself:
fresh market data, a forecast with honest error bars, a battery backtest with
documented assumptions, and an agent whose answers are *measured*, not just demoed.
The wow effect comes from rigor + a live, self-operating pipeline — not from hype.

## Hard constraints

- **0 € total cost.** No paid services, no cloud subscriptions, no API keys with billing.
- **GitHub-only infrastructure.** GitHub Actions (scheduler + compute), GitHub Pages
  (hosting), GitHub Issues (alerting). No Azure, no other cloud.
- **Public repo** (required for free unlimited Actions + Pages).
- **LLM inference is local-only** (Ollama). The live site shows cached, evaluated
  agent outputs; visitors can reproduce the agent locally.
- **Free data only:** SMARD (Bundesnetzagentur, CC BY 4.0, no key required).

## Architecture (pipeline-as-code, no servers)

```
GitHub Actions (cron, hourly/daily)
  └─ ingest:   SMARD API → validated Parquet in repo (git scraping pattern)
  └─ forecast: LightGBM day-ahead price forecast, walk-forward validated
  └─ backtest: battery arbitrage on forecasts vs. perfect-foresight benchmark
  └─ publish:  JSON artifacts → static dashboard → GitHub Pages
  └─ quality:  data checks; failures open GitHub Issues automatically

Local only (reproducible by anyone):
  └─ agent:    Ollama + MCP server exposing data/forecast tools
  └─ evals:    eval harness with error analysis; results published to the site
```

## Engineering standards (non-negotiable)

- Honest measurement: baselines first (naive, seasonal-naive); beating them is a
  finding, not an assumption. Negative results get reported, not hidden.
- No lookahead: forecast features restricted to information available before
  day-ahead auction gate closure (12:00 CET, day D-1).
- New logic ships with tests. CI runs from the first push.
- Conventional commits, English. Small atomic commits. Work on feat/ branches.

## Data source facts (verified 2026-07-03)

- Index:  `https://www.smard.de/app/chart_data/{filter}/DE/index_hour.json`
  → `{"timestamps": [<ms epoch of week starts>]}`
- Data:   `https://www.smard.de/app/chart_data/{filter}/DE/{filter}_DE_hour_{ts}.json`
  → `{"meta_data": ..., "series": [[ms_epoch, value|null] × 168]}`
- Filter 4169 = day-ahead price DE/LU (€/MWh), filter 410 = total grid load (MWh).
  Further filter IDs (generation mix, forecasts) must be probed and verified in
  Phase 1 — do not trust undocumented ID lists.
