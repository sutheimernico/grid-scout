import { useEffect, useState } from "react";
import { HeroChart } from "../charts/HeroChart";
import { fmtDateTime, fmtNum } from "../lib/format";
import { pickHeroWindow } from "../lib/hero";
import type { ForecastData, HealthData } from "../types";

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
}: {
  forecast: { state: "loading" | "missing" } | { state: "ready"; data: ForecastData };
  health: { state: "loading" | "missing" } | { state: "ready"; data: HealthData };
}) {
  const days = useHeroDays();
  const ready = forecast.state === "ready" ? forecast.data : null;
  const win = ready ? pickHeroWindow(ready.recent, days) : null;
  const nHours = ready?.eval.models.lgbm_point?.n;

  return (
    <section className="hero" id="top" aria-label="Forecast against cleared prices">
      <div className="wrap">
        <div className="hero-head">
          <h1>Tomorrow&apos;s German power price, forecast before the auction closes.</h1>
          <div>
            <p className="lede">
              A LightGBM model predicts all 24 hourly day-ahead prices
              {ready && nHours
                ? `, validated walk-forward over ${ready.eval.eval_period.n_days} days (${fmtNum(nHours)} out-of-sample hours)`
                : ""}
              , scored against three baselines and recorded live every morning. It runs on GitHub
              Actions alone, with no server.
            </p>
            {health.state === "ready" && (
              <p className="hero-meta">
                Pipeline last ran {fmtDateTime(health.data.generated_at)} · data: SMARD / Bundesnetzagentur (CC BY
                4.0)
              </p>
            )}
          </div>
        </div>

        {win ? (
          <>
            <HeroChart window={win} height={days === 2 ? 320 : 380} />
            <p className="small" style={{ marginTop: 12, maxWidth: "74ch" }}>
              Backtest, not live: the last {win.days.length} complete delivery days of the walk-forward evaluation,
              forecast made without knowing the cleared prices. The band is the raw model p10 to p90.
            </p>
          </>
        ) : null}
      </div>
    </section>
  );
}
