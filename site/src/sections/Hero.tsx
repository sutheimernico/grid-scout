import { useEffect, useState } from "react";
import { HeroChart } from "../charts/HeroChart";
import { LineChart } from "../charts/LineChart";
import { fmtCalendarDate, fmtDateTime, fmtHourLabel, fmtNum } from "../lib/format";
import { hasRecordedForecasts, lastScoredDay, liveTomorrow } from "../lib/live";
import type { Loadable } from "../lib/useData";
import { pickHeroWindow } from "../lib/hero";
import type { ForecastData, ForwardLedgerData, HealthData } from "../types";

export function Masthead() {
  return (
    <header className="masthead">
      <div className="wrap">
        <a className="wordmark" href="#top" aria-label="grid-scout, top of page">
          <svg width="30" height="24" viewBox="0 0 30 24" aria-hidden="true">
            <line x1="1" y1="16" x2="29" y2="16" stroke="currentColor" strokeWidth="1.5" />
            <path d="M1 12 L6 5 L11 14 L16 3 L21 19 L25 9 L29 11" fill="none" stroke="var(--volt)" strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round" />
          </svg>
          grid-scout
        </a>
        <nav aria-label="Sections">
          <a href="#forecast">Forecast</a>
          <a href="#ledger">Ledger</a>
          <a href="#battery">Battery</a>
          <a href="#market">Market</a>
          <a href="#agent">Agent</a>
          <a href="#pipeline">Pipeline</a>
          <a href="https://github.com/sutheimernico/grid-scout">Source</a>
        </nav>
      </div>
    </header>
  );
}

/** Two days on a phone: three days of hourly points do not leave a finger
 *  anything to point at in 360 px. */
function useHeroDays(): number {
  const [days, setDays] = useState(3);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(max-width: 560px)");
    const apply = () => setDays(mq.matches ? 2 : 3);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);
  return days;
}

export function Hero({
  forecast,
  health,
  ledger,
}: {
  forecast: Loadable<ForecastData>;
  health: Loadable<HealthData>;
  ledger: Loadable<ForwardLedgerData>;
}) {
  const days = useHeroDays();
  const ready = forecast.state === "ready" ? forecast.data : null;
  const win = ready ? pickHeroWindow(ready.recent, days) : null;
  const nHours = ready?.eval.models.lgbm_point?.n;
  const led = ledger.state === "ready" ? ledger.data : null;
  const tomorrow = liveTomorrow(led);
  const recording = hasRecordedForecasts(led);

  return (
    <section className="hero" id="top" aria-label="Forecast against cleared prices">
      <div className="wrap">
        <div className="hero-head">
          {tomorrow ? (
            <h1>Tomorrow&apos;s German power price, forecast before the auction closes.</h1>
          ) : (
            <h1>Germany&apos;s day-ahead power price, forecast hour by hour and scored against what cleared.</h1>
          )}
          <div>
            <p className="lede">
              Hourly day-ahead price forecasts from a LightGBM model
              {ready && nHours
                ? `, validated walk-forward over ${ready.eval.eval_period.n_days} days (${fmtNum(nHours)} out-of-sample hours)`
                : ""}
              , compared with naive and linear baselines.{" "}
              {recording
                ? "A forward ledger records every forecast before the auction closes and scores it afterwards."
                : "A forward ledger that records each forecast before the auction closes, and scores it afterwards, starts with the first daily run."}{" "}
              It runs on GitHub Actions alone, with no server.
            </p>
            {health.state === "ready" && (
              <p className="hero-meta">
                Pipeline last ran {fmtDateTime(health.data.generated_at)} · data: SMARD / Bundesnetzagentur (CC BY
                4.0)
              </p>
            )}
          </div>
        </div>

        {tomorrow && led && <Tomorrow latest={tomorrow} ledger={led} />}

        {win ? (
          <>
            <HeroChart window={win} height={days === 2 ? 320 : 380} yearMae={ready?.eval.models.lgbm_point?.mae} />
            <p className="small" style={{ marginTop: 12, maxWidth: "76ch" }}>
              Backtest, not live: the last {win.days.length} complete delivery days of the walk-forward evaluation. The
              forecast is the full model, which assumes the TSOs&apos; generation forecast for the delivery day is
              known; the band is its raw p10 to p90.
            </p>
          </>
        ) : null}
      </div>
    </section>
  );
}

/* The one place the page may say "tomorrow": the ledger's open forecast, drawn
   without a cleared-price line because there is none yet. */
function Tomorrow({ latest, ledger }: { latest: NonNullable<ForwardLedgerData["latest"]>; ledger: ForwardLedgerData }) {
  const last = lastScoredDay(ledger);
  return (
    <div className="tomorrow">
      <p className="subhead" style={{ marginTop: 0 }}>
        Delivery day {fmtCalendarDate(latest.target_date)}: forecast recorded {fmtDateTime(latest.generated_at_utc)}.
        The day-ahead auction clears at 12:00 and no cleared price exists yet.
      </p>
      <div className="chart-plate">
        <LineChart
          height={260}
          endLabels
          series={[
            { key: "pred", label: "Forecast", color: "var(--volt)", values: latest.pred_model as (number | null)[], width: 2.75 },
            { key: "naive", label: "Naive", color: "var(--naive)", values: latest.pred_naive as (number | null)[], dashed: true },
          ]}
          xLabels={latest.hours_local.map(fmtHourLabel)}
          unit="€/MWh"
          xTickEvery={3}
        />
      </div>
      {last && last.maeModel != null && last.maeNaive != null && (
        <p className="small" style={{ marginTop: 10 }}>
          Last scored day, {fmtCalendarDate(last.date)}: forecast error {fmtNum(last.maeModel, 1)} €/MWh against{" "}
          {fmtNum(last.maeNaive, 1)} for the naive forecast.
        </p>
      )}
    </div>
  );
}
