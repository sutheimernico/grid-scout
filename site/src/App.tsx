import { useEffect, useState } from "react";
import { useArtifact } from "./lib/useData";
import type { AgentData, BatteryData, ForecastData, ForwardLedgerData, HealthData, MarketData, UptimeData } from "./types";
import { Agent } from "./sections/Agent";
import { Battery } from "./sections/Battery";
import { Evidence, Segments } from "./sections/Evidence";
import { Health } from "./sections/Health";
import { Hero, Masthead } from "./sections/Hero";
import { Ledger } from "./sections/Ledger";
import { Market } from "./sections/Market";
import { Pending } from "./ui";

export { sumMembers } from "./sections/Market";

export const SETTLE_TIMEOUT_MS = 2500;

export default function App() {
  const market = useArtifact<MarketData>("market.json");
  const forecast = useArtifact<ForecastData>("forecast.json");
  const battery = useArtifact<BatteryData>("battery.json");
  const agent = useArtifact<AgentData>("agent.json");
  const health = useArtifact<HealthData>("health.json");
  const ledger = useArtifact<ForwardLedgerData>("forward_ledger.json");
  const uptime = useArtifact<UptimeData>("uptime.json");

  // Render the body in one pass once every artifact has settled. Filled in one
  // by one, the sections pushed each other down (measured CLS ~0.5); all seven
  // files together are ~40 kB gzipped, so waiting for the slowest costs little.
  // The timeout keeps one hung request from blanking the whole page.
  const [waitedLongEnough, setWaitedLongEnough] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setWaitedLongEnough(true), SETTLE_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, []);
  const settled =
    waitedLongEnough ||
    [market, forecast, battery, agent, health, ledger, uptime].every((a) => a.state !== "loading");

  if (!settled) {
    return (
      <>
        <Masthead />
        <div className="wrap loading">Loading pipeline artifacts…</div>
      </>
    );
  }

  return (
    <>
      <Masthead />
      <main>
        <Hero forecast={forecast} health={health} ledger={ledger} />

        {forecast.state === "ready" ? (
          <>
            <Evidence data={forecast.data} />
            <Segments segments={forecast.data.segments} />
          </>
        ) : (
          <section className="band plate" id="forecast">
            <div className="wrap">
              <Pending what="forecast evaluation" state={forecast.state} />
            </div>
          </section>
        )}

        <Ledger ledger={ledger} />

        {battery.state === "ready" ? (
          <Battery data={battery.data} />
        ) : (
          <section className="band plate" id="battery">
            <div className="wrap">
              <Pending what="battery backtest" state={battery.state} />
            </div>
          </section>
        )}

        {market.state === "ready" ? (
          <Market data={market.data} />
        ) : (
          <section className="band" id="market">
            <div className="wrap">
              <Pending what="market data" state={market.state} />
            </div>
          </section>
        )}

        {agent.state === "ready" ? (
          <Agent data={agent.data} />
        ) : (
          <section className="band tint" id="agent">
            <div className="wrap">
              <Pending what="agent evaluation" state={agent.state} />
            </div>
          </section>
        )}

        <Health health={health} uptime={uptime} />
      </main>

      <footer className="footer">
        <div className="wrap">
          <p>
            Data: <a href="https://www.smard.de">SMARD</a>, Bundesnetzagentur, CC BY 4.0 · hourly, Europe/Berlin. Built
            as a 0-€ pipeline: GitHub Actions + GitHub Pages, local-only LLM tooling. Honest by design — negative
            results stay in the report.
          </p>
          <p>
            <a href="https://github.com/sutheimernico/grid-scout">Source on GitHub</a>
          </p>
        </div>
      </footer>
    </>
  );
}
