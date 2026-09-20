# Plan: Live Proof + Analytical Depth — grid-scout

**Date:** 2026-07-20 · **Status:** awaiting go · **Executor:** any capable agent (self-contained — no session context required)

## Context (verified 2026-07-20 by code review + live checks)

grid-scout is Nico's flagship portfolio piece: a self-operating German power-market intelligence system on a 0-€ GitHub-only stack (Actions = compute/scheduler, Pages = frontend, Issues = alerting). Public repo, live at sutheimernico.github.io/grid-scout. Pipeline: SMARD ingest (19 series, keyless API) → validation → LightGBM walk-forward forecast → exact-LP battery arbitrage backtest → JSON export → React/Vite site with hand-rolled SVG charts → commit-back to `main` (`[skip ci]`) → Pages deploy. Ollama agent section with programmatically graded evals. 76 Python tests + chart-math vitest, all green.

**Verified live facts:** the scheduled pipeline (`47 */3 * * *` + weekly full eval Mondays) has run 112 times since 2026-07-04 with 0 failures since 2026-07-06; site data was ~2h fresh at review time. **The local clone is ~111 commits behind origin/main** (bot data commits) — see execution rules.

The gaps, in one line each:
- All forecast/battery numbers on the site are a **frozen weekly backtest** — no live "tomorrow" forecast, no growing forward track record (deferred in PLAN.md's own outcome section).
- The genuinely impressive fact — two weeks of unbroken self-operation — is **invisible to visitors** (one "last ran" timestamp).
- `ingest_all` has **no per-series fault isolation** (`src/gridscout/smard/ingest.py`): one glitchy SMARD response aborts the whole 3-hourly run.
- The health panel shows a **permanent false alarm**: `gen_nuclear` (filter 1224) is frozen since Germany's 2023 nuclear phase-out but renders as generic red "stale" — undermining the honesty narrative.
- `export_health` ignores **derived-report freshness**: if the weekly full eval silently died, the site would show stale forecast numbers under an all-green health panel.
- Promised battery **sensitivity analysis** (efficiency, 2h/4h duration; PLAN.md Phase 3) was never delivered. `App.tsx` (370 lines) has **no component tests**. Pages deploy step has no retry (the only 6 failures ever were deploy races).

## Goal

Make the site *prove* it is alive instead of asserting it, and add the analytical depth that separates it from a pretty one-shot backtest: a daily forward-forecast ledger scored against reality, an uptime heatmap, deterministic market explanations, segmented error analysis — plus the robustness fixes that protect the 3-hourly heartbeat.

## Execution rules

- **First action: `git fetch && git pull --ff-only` on `main`** — the bot is ~111 commits ahead; never work from the stale state. Then branch `feat/live-proof`.
- Public repo: no secrets anywhere (SMARD is keyless; nothing here needs a key), no personal data, commit messages English/Conventional. **Never manually edit or commit files under `data/` or `reports/`** — those belong to the bot; a feature branch touching them guarantees conflicts.
- Workflow changes (`.github/workflows/pipeline.yml`) only take effect once merged to `main` — keep workflow-file diffs minimal and push all non-trivial logic into testable Python CLI commands (`src/gridscout/cli.py`) instead of bash.
- Gates after every task: `uv run pytest && uv run ruff check .`; site tasks additionally `cd site && npm test && npm run build`.
- Merge/PR is Nico's call (public flagship — he reviews before anything lands on `main`).

---

## Phase A — Protect the heartbeat

### Task 1: Per-series fault isolation in ingest
**Files:** `src/gridscout/smard/ingest.py::ingest_all`, tests.
Wrap the per-series ingest in try/except: collect `(series, error)` failures, continue with remaining series, log a summary at the end, exit non-zero if any failed (so the workflow's existing Issue-alert still fires) — but only **after** every series was attempted. Existing Parquet stays untouched on failure (validation already runs pre-write; keep it that way).
**Accept:** new test: series 3 of 5 raises → series 4–5 still ingested, run reports the one failure, exit code non-zero.

### Task 2: Discontinued-series semantics (kill the false alarm)
**Files:** `src/gridscout/smard/filters.py` (`SeriesSpec`), `src/gridscout/export.py::export_health`, `site/src/App.tsx` health section, tests.
Add `discontinued: str | None` (human-readable reason) to `SeriesSpec`; set it for `gen_nuclear` ("German nuclear phase-out, April 2023"). Health export emits status `discontinued` instead of `stale` for such series; the site renders it neutrally (grey, with the reason) instead of red.
**Accept:** health panel no longer shows a permanent red row; a genuinely stale non-discontinued series still alarms (test both).

### Task 3: Freshness for derived reports
**Files:** `src/gridscout/export.py::export_health`, `site/src/App.tsx`, tests.
Include `reports/forecast_eval.json`, `battery_backtest.json`, `agent_eval.json` in the health export with their generation timestamps and an expected cadence (weekly → warn beyond 8 days, red beyond 15). Site shows them in the health panel.
**Accept:** a mocked 10-day-old forecast_eval turns its health row yellow while raw series stay green.

### Task 4: Deploy retry
**Files:** `.github/workflows/pipeline.yml` (deploy job).
Retry the Pages deploy once after a short wait on failure (the only historical failure mode was a transient "Deployment failed, try again later" race). Keep it minimal: `continue-on-error` on the first attempt + a guarded second attempt step.
**Accept:** workflow YAML lints (`actionlint` if available, else careful review); logic is two steps, no new bash complexity.

### Task 5: Component tests for App.tsx
**Files:** `site/src/App.test.tsx` (new), possibly small extractions from `site/src/App.tsx` for testability (keep diffs minimal).
Cover with @testing-library/react (add as devDependency): loading state, artifact-missing → "pending" panel degradation, ready-state rendering per section, and the `sumMembers` generation-mix aggregation.
**Accept:** the highest-LOC least-tested file has its core states pinned; `npm test` green.

---

## Phase B — The forward-test ledger (backtest → living proof)

Honesty constraint for everything in this phase: a prediction only counts if it was made **before** the information it predicts existed. The German day-ahead auction closes 12:00 CET (results ~12:45 CET). The daily forecast run must therefore complete before 12:00 CET and must only use features available at run time (the morning-published wind/solar/load forecast series already ingested — never realized prices of the target day).

### Task 6: Daily forward forecast + ledger
**Files:** new `src/gridscout/forecast/forward.py`, new CLI command `gridscout forecast-tomorrow`, `.github/workflows/pipeline.yml` (new daily job), tests.
- `forecast-tomorrow`: load the current trained model artifacts, build features for the next delivery day from data available *now* (guard: assert no feature column derives from the target day's realized series; reuse the existing leakage-guard helpers in `forecast/features.py`), predict 24 hourly day-ahead prices, append one record to `reports/forward_ledger.parquet`: `{generated_at_utc, target_date, predictions[24], model_version/hash, feature_snapshot_meta}`. Idempotent: second run on the same day for the same target overwrites its own pending record, never a scored one.
- Workflow: new job/schedule `23 9 * * *` UTC (11:23 CET summer / 10:23 CET winter — both safely before auction close; add a comment explaining this), running only the forecast + commit-back.
- Scoring: in the existing 3-hourly run, a new step `gridscout score-ledger` scores every unscored ledger entry whose target day now has realized day-ahead prices: per-entry MAE, naive-baseline MAE (same-hour previous day), seasonal-naive MAE — appended to the record. Pure, tested logic; the bash in the workflow stays one line.
**Accept:** unit tests with synthetic ledger (pending → scored transition, idempotency, leakage guard trips on a poisoned feature set); one local dry run of `forecast-tomorrow` against pulled real data completes and writes a valid record (delete the record before committing — the bot owns `reports/`).

### Task 7: Live-forecast panel on the site
**Files:** `src/gridscout/export.py` (ledger → `forward_ledger.json`), `site/src/App.tsx` + new chart in `site/src/charts/`, vitest.
Forecast section gains a "Live-Forecast" block: tomorrow's predicted curve (and, once known, the realized day-ahead curve overlaid); a track-record strip: "Live seit N Tagen · N Forecasts · MAE model vs. naive (kumulativ + letzte 7 Tage)"; honest empty state before the first ledger entries mature ("Forward-Test läuft seit …, erste Scores ab …"). Visual language matches the existing hand-rolled SVG style.
**Accept:** renders all three states (no ledger / pending only / scored) from fixture JSON in vitest; site build green.

---

## Phase C — Visible proof + analytical depth

### Task 8: Uptime heatmap (cheapest, highest-leverage)
**Files:** `src/gridscout/export.py` (new `export_uptime`), new small chart component, `site/src/App.tsx`, tests.
At export time, derive a per-day run count from the git history of bot commits (`git log --format=%cI --grep="skip ci"` equivalent via subprocess, or count refresh timestamps already embedded in artifacts if simpler — pick one, document it) and emit `uptime.json`: date → runs. Site renders a contribution-graph-style calendar since 2026-07-04 with a caption ("Pipeline läuft unbeaufsichtigt alle 3h — jede Zelle ein Tag"). Days with fewer runs than expected show honestly lighter.
**Accept:** heatmap renders from fixture data; generated from real history in the pipeline; a visitor sees two-plus weeks of dense green within 2 seconds.

### Task 9: Deterministic market captions
**Files:** reuse logic from `src/gridscout/agent/tools.py::explain_price_context` — extract the pure parts into `src/gridscout/analysis/captions.py` (agent keeps calling the shared code), `export.py`, `site/src/App.tsx`, tests.
Generate a rule-based German caption for the current market window ("Preis-Tief 14 Uhr bei hoher Solareinspeisung (X GW); teuerste Stunde 20 Uhr, Residuallast Y GW") and show it under the Market charts. No LLM — deterministic, testable string assembly from the same numbers the charts show.
**Accept:** caption unit tests for spike/negative-price/normal days; caption visibly on the site; agent tests still green after the extraction.

### Task 10: Segmented forecast error analysis
**Files:** new `src/gridscout/forecast/segments.py`, `export.py`, small site panel, tests.
From the existing walk-forward `predictions.parquet`: MAE by hour-of-day, by weekday, and by price regime (negative-price hours / top-decile-volatility days / normal) — model vs. both naive baselines per segment. Export as JSON; site shows a compact table or small-multiple bars ("wo das Modell gewinnt — und wo nicht": honest segments where naive wins stay visible).
**Accept:** hand-computed segment values on a small fixture; panel renders; no aggregate-only storytelling left.

### Task 11: Battery sensitivity sweep (close the PLAN.md Phase-3 gap)
**Files:** `src/gridscout/battery/` (sweep runner around the existing LP), `export.py`, site panel, tests; wire into the weekly full-eval workflow step.
Grid: efficiency {0.85, 0.90, 0.95} × duration {2h, 4h} → revenue per combination (perfect + model-driven). Runs only in the weekly full eval (cost control on Actions minutes).
**Accept:** 6-cell result matrix on the site; values reproduced by test on a fixture window; weekly job runtime increase documented in the outcome section.

### Task 12 (stretch): Chart interactivity
**Files:** `site/src/charts/`, `App.tsx`, vitest.
Tooltips with exact values (SVG hover, no library) + a 7d/30d/90d range switcher on Market charts. Only if Tasks 1–11 are done and green; keep the hand-rolled-SVG ethos (no chart library).
**Accept:** keyboard/mouse tooltip works, range switch re-scales axes; tests for the scale math extensions.

---

## Explicitly out of scope (decided, do not do here)
- **In-browser WebLLM agent Q&A** — highest differentiation but a scope jump (model download size, WebGPU variance); revisit as its own project phase after this plan matures.
- **ENTSO-E neighbor-zone prices / interconnector analysis** — new data source + API key + breaks the deliberate "SMARD-only, keyless" constraint; separate decision for Nico.

## Verification before completion
1. All gates green (pytest, ruff, vitest, site build). Fresh `git pull --ff-only` + rebase of the branch right before finishing (the bot moved `main` meanwhile — guaranteed).
2. Local dry runs: `gridscout forecast-tomorrow` (record deleted afterwards), `score-ledger` on fixtures, export of uptime/captions/segments from real pulled data.
3. Manual site pass via `npm run dev`: all new panels render with real exported JSON, including their empty states.
4. Append an **Outcome** section here: what was built, deviations, Actions-minutes impact, screenshots list for Nico's review.
5. Update `PLAN.md` outcome section (deferred items now delivered) and README (new panels, "bot commits every 3h — always pull before local work" note).

## Needs Nico (not agent-executable)
- Go for this plan; PR review + merge to `main` (public flagship — workflow changes activate only after merge; the forward ledger starts growing from merge day, its value compounds weekly).
- Portfolio link to grid-scout (still open from 2026-07-04).
- Decision whether the ENTSO-E extension is ever wanted (registration = his email).
