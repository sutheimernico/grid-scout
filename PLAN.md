# PLAN — grid-scout build loop

Source of truth for the autonomous build loop. Work phases top to bottom.
Each phase ends with: tests green, self-review of the diff, conventional commit
on a feat/ branch, merge to main, progress log entry here.

## Phase status

- [x] Phase 0 — Scaffold
- [x] Phase 1 — SMARD ingestion (backfill done, validated, data current)
- [x] Phase 2 — Forecast harness (code done; first real eval run pending)
- [x] Phase 3 — Battery arbitrage backtest (real run: capture 94.1%, edge +4,721 €/MW/y)
- [x] Phase 4 — Static dashboard (built, screenshot-verified, palette validated)
- [ ] Phase 5 — GitHub: BLOCKED on user running `gh repo create` (classifier denies
      public-repo creation by agent); workflows ready on main
- [x] Phase 6 — Agent + MCP server + evals (code done; first real eval running)
- [ ] Phase 7 — Wow polish, docs, final verification

## Phase 1 — SMARD ingestion

Goal: `gridscout ingest` fetches hourly series from SMARD into partitioned
Parquet under `data/`, idempotent and resumable.

- Probe and verify filter IDs: day-ahead price (4169 ✓), grid load (410 ✓),
  generation by source (wind onshore/offshore, solar, brown/hard coal, gas,
  nuclear-era zeros ok, hydro, biomass), plus SMARD *forecast* filters
  (prognosticated load / wind / solar) — these matter for leakage-free features.
  Record verified IDs in `src/gridscout/smard/filters.py` with human labels.
- httpx client with retry/backoff, weekly-file caching (skip already-complete weeks).
- Validation: monotone timestamps, plausible ranges, null-handling policy.
- Storage: one Parquet per series under `data/{series}.parquet` (hourly, UTC).
- Backfill: ≥3 full years for training + current partial week.
- Tests: recorded JSON fixtures, no live HTTP in tests.

Acceptance: fresh clone → `uv run gridscout ingest` → Parquet files appear;
re-run is a no-op except current week; pytest green.

## Phase 2 — Forecast harness

Goal: day-ahead price forecast (24 hourly prices for day D, produced with only
information available before D-1 12:00 CET), honestly validated.

- Baselines: naive (yesterday), seasonal-naive (same weekday last week).
- Model: LightGBM with calendar features + SMARD day-ahead *forecast* series
  (load/wind/solar prognosis) — never realized values from the target day.
- Walk-forward validation over ≥1 year of daily refits (expanding window),
  MAE/RMSE + pinball loss for quantiles (p10/p50/p90).
- Report: `reports/forecast_eval.json` + markdown summary. If LightGBM does not
  beat seasonal-naive, that is the reported finding.
- Tests: leakage guard test (feature matrix must contain no target-day realized
  data), deterministic seed, metric math.

## Phase 3 — Battery arbitrage backtest

Goal: quantify what the forecast is worth with a 1 MW / 2 MWh battery trading
the day-ahead auction.

- Strategy: daily schedule optimization (charge cheapest hours, discharge most
  expensive; LP or exact greedy for single battery) on (a) perfect foresight,
  (b) forecast prices. Round-trip efficiency ~86%, cycle limit 1/day, no grid fees
  modeled — assumptions documented.
- Metrics: €/MW/year, capture rate = forecast-strategy revenue / perfect-foresight
  revenue. Sensitivity: efficiency, 2h vs 4h duration.
- Tests: known-price toy cases with hand-computed optimal schedules.

## Phase 4 — Static dashboard

Goal: a fast, striking static site reading pipeline JSON artifacts.

- Stack: Vite + React 19 + TS (matches existing skill set; no SSR needed).
- Views: current market (price + generation mix), forecast vs. actuals with
  quantile bands, battery backtest results, agent eval results (Phase 6),
  pipeline health (last run, data freshness).
- Design: dataviz skill + dark, technical aesthetic; must not look templated.
- Artifacts contract: pipeline writes `site/public/data/*.json`.

## Phase 5 — GitHub: repo, Actions, Pages, alerts

- Create public repo `sutheimernico/grid-scout`, push, branch protection off (solo).
- CI: lint + tests on PR/push (starts as soon as repo exists — do this at end of
  Phase 1, not later).
- Scheduled workflow: ingest → forecast → backtest → build site → deploy Pages.
  Commits data artifacts back to main (git scraping pattern; [skip ci] guard).
- Failure path: workflow failure or data-quality violation opens a GitHub Issue
  (dedup: update existing open issue instead of spamming).
- Badges: pipeline status, data freshness, test coverage.

## Phase 6 — Agent + MCP server + evals

Goal: local agent that answers market questions via tools, with a measured
error rate — the 2026 differentiator.

- MCP server (Python SDK) exposing tools: query series, get forecast + errors,
  explain price drivers for a window, battery backtest lookup.
- Agent: Ollama (qwen2.5:7b on disk; consider pulling a newer small model, decide
  then), tool-calling loop, answers grounded in tool results only.
- Eval set: ~30 questions with gold answers derived from the data (factual,
  analytical, out-of-scope traps). Grader: exact/tolerance checks where possible,
  LLM-judge only where unavoidable. Error analysis writeup: failure taxonomy.
- Publish: eval results + transcripts (curated) as JSON to the dashboard.

## Phase 7 — Wow polish, docs, final verification

- README with architecture diagram, honest findings summary, screenshots.
- Dashboard visual polish pass (motion, theming — portfolio-grade).
- Full fresh-clone verification: setup docs actually work.
- Final self-review sweep + verification-before-completion gate.

## Progress log

- 2026-07-03: Phase 0 done — repo scaffolded (uv, pytest, ruff, docs), SMARD API
  format verified live (4169 price, 410 load; weekly 168-point hourly JSON).
- 2026-07-03: Phase 1 code done — all 19 filter IDs probed live (solar forecast
  is 125, NOT the OpenAPI enum's 126 which is a negated aggregate; full history
  since 2014-12-29). Client with disk cache + retry, incremental parquet ingest
  (trailing-2-week refresh, revisions win, trailing nulls dropped, interior
  nulls kept), structural validation. 17 tests, ruff clean, merged to main.
  Live backfill (~3.5k requests) running; DST week-length assumption gets
  verified by validation during that run.
- 2026-07-03: Backfill complete + validated (5.5y deep series, 2.5y gen mix,
  11 DST transitions clean). Found: SMARD hourly price has a rolling ~2-day
  settlement hole behind tomorrow's auctioned prices (15-min market coupling);
  ingest handles it (interior nulls kept, trailing refresh fills them).
- 2026-07-03: Phase 2+3 code done — leakage-guarded feature matrix (perturbation
  test enforces the availability contract), naive/seasonal-naive baselines,
  LightGBM point+quantile, expanding walk-forward, eval report with rule-based
  verdict; battery LP (exact, hand-computed test optima) with perfect/model/
  naive schedules. First real eval running.
