import { LineChart } from "./charts/LineChart";
import { StackedArea } from "./charts/StackedArea";
import { useArtifact } from "./lib/useData";
import type { AgentData, BatteryData, ForecastData, HealthData, MarketData } from "./types";

const COLORS = {
  model: "var(--s1)",
  baseline: "var(--s3)",
  reference: "var(--ink-2)",
};

/* Generation mix: 11 raw series folded to 6 groups (≤ 6 categorical slots),
   fixed entity→color mapping, stack order bottom = steady, top = volatile. */
const GEN_GROUPS: { key: string; label: string; color: string; members: string[] }[] = [
  { key: "other_conv", label: "Other conventional", color: "#9085e9", members: ["gen_other_conventional", "gen_pumped_storage", "gen_nuclear"] },
  { key: "coal", label: "Coal", color: "#e66767", members: ["gen_lignite", "gen_hard_coal"] },
  { key: "gas", label: "Natural gas", color: "#d95926", members: ["gen_gas"] },
  { key: "other_renew", label: "Hydro, biomass & other renewables", color: "#008300", members: ["gen_hydro", "gen_biomass", "gen_other_renewable"] },
  { key: "wind", label: "Wind (on- + offshore)", color: "#199e70", members: ["gen_wind_onshore", "gen_wind_offshore"] },
  { key: "solar", label: "Solar", color: "#c98500", members: ["gen_solar"] },
];

const hourFmt = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", timeZone: "Europe/Berlin" });

export default function App() {
  const market = useArtifact<MarketData>("market.json");
  const forecast = useArtifact<ForecastData>("forecast.json");
  const battery = useArtifact<BatteryData>("battery.json");
  const agent = useArtifact<AgentData>("agent.json");
  const health = useArtifact<HealthData>("health.json");

  return (
    <>
      <header className="masthead">
        <h1>
          <span className="prompt">▸</span> grid-scout
        </h1>
        <p>
          Self-operating intelligence on the German electricity market: live SMARD data, a
          walk-forward-validated day-ahead price forecast, and a battery-arbitrage backtest that
          prices what the forecast is actually worth. Runs entirely on GitHub Actions — no servers.
        </p>
        {health.state === "ready" && (
          <div className="meta">
            pipeline last ran {new Date(health.data.generated_at).toLocaleString("en-GB", { timeZone: "Europe/Berlin" })} ·
            data: SMARD / Bundesnetzagentur (CC BY 4.0)
          </div>
        )}
      </header>

      {market.state === "ready" && forecast.state === "ready" && battery.state === "ready" && (
        <section className="section" aria-label="Headline figures">
          <div className="tile-row">
            <Tile
              label="Day-ahead price (latest)"
              value={market.data.kpis.latest_price_eur_mwh.toFixed(2)}
              unit="€/MWh"
              hint={new Date(market.data.kpis.latest_price_at).toLocaleString("en-GB", {
                timeZone: "Europe/Berlin",
              })}
            />
            <Tile
              label="Negative-price hours (YTD)"
              value={String(market.data.kpis.negative_price_hours_ytd)}
              hint="hours below 0 €/MWh this year"
            />
            <Tile
              label="Renewables share (24h)"
              value={(market.data.kpis.renewables_share_last_24h * 100).toFixed(0)}
              unit="%"
              hint="of measured generation"
            />
            <Tile
              label="Forecast skill vs naive"
              value={`+${forecast.data.eval.skill.lgbm_vs_naive_pct.toFixed(1)}`}
              unit="%"
              hint={`MAE ${forecast.data.eval.models.lgbm_point.mae.toFixed(2)} €/MWh, walk-forward, 1y`}
              good
            />
            <Tile
              label="Battery capture rate"
              value={(battery.data.summary.capture_rate_model * 100).toFixed(1)}
              unit="%"
              hint="of perfect-foresight revenue"
              good
            />
          </div>
        </section>
      )}

      <section className="section">
        <div className="kicker">Market</div>
        <h2>The last 14 days on the German grid</h2>
        <p className="sub">
          Day-ahead auction prices and the generation mix behind them. Price valleys line up with
          solar peaks — negative prices happen when renewables flood the market.
        </p>
        {market.state === "ready" ? (
          <>
            <div className="panel">
              <p className="panel-title">Day-ahead price</p>
              <p className="panel-sub">€/MWh, hourly, Europe/Berlin</p>
              <LineChart
                series={[
                  { key: "price", label: "Day-ahead price", color: COLORS.model, values: market.data.hourly.price },
                ]}
                xLabels={market.data.hourly.timestamps.map(hourFmt)}
                unit="€/MWh"
              />
            </div>
            <div className="panel">
              <p className="panel-title">Generation mix</p>
              <p className="panel-sub">MWh per hour, measured, grouped from 11 SMARD series</p>
              <StackedArea
                series={GEN_GROUPS.map((g) => ({
                  key: g.key,
                  label: g.label,
                  color: g.color,
                  values: sumMembers(market.data.hourly.generation, g.members),
                }))}
                xLabels={market.data.hourly.timestamps.map(hourFmt)}
                unit="MWh"
                formatValue={(v) => `${Math.round(v / 1000)}k`}
              />
              <div className="legend">
                {[...GEN_GROUPS].reverse().map((g) => (
                  <span className="item" key={g.key}>
                    <span className="swatch" style={{ background: g.color }} /> {g.label}
                  </span>
                ))}
              </div>
            </div>
          </>
        ) : (
          <Pending what="market data" state={market.state} />
        )}
      </section>

      <section className="section">
        <div className="kicker">Forecast</div>
        <h2>Predicting tomorrow&apos;s prices — measured honestly</h2>
        <p className="sub">
          A LightGBM model predicts all 24 hourly prices before the day-ahead auction closes, using
          only information available at that moment (a perturbation test enforces this). Every
          number below is out-of-sample: expanding walk-forward over a full year, refit weekly.
        </p>
        {forecast.state === "ready" ? (
          <>
            <div className="panel">
              <p className="panel-title">Forecast vs. reality — last 4 weeks of the eval period</p>
              <p className="panel-sub">
                point forecast with p10–p90 band · band coverage{" "}
                {(forecast.data.eval.quantiles.coverage_p10_p90 * 100).toFixed(0)}% (target 80% — the
                band is honestly too narrow)
              </p>
              <LineChart
                series={[
                  { key: "actual", label: "Actual", color: COLORS.model, values: forecast.data.recent.actual },
                  { key: "pred", label: "Predicted", color: COLORS.baseline, values: forecast.data.recent.predicted },
                ]}
                band={{
                  upper: forecast.data.recent.q90,
                  lower: forecast.data.recent.q10,
                  color: "#3987e5",
                  label: "p10–p90",
                }}
                xLabels={forecast.data.recent.timestamps.map(hourFmt)}
                unit="€/MWh"
              />
              <div className="legend">
                <span className="item"><span className="swatch line" style={{ background: COLORS.model }} /> Actual</span>
                <span className="item"><span className="swatch line" style={{ background: COLORS.baseline }} /> Predicted</span>
                <span className="item"><span className="swatch" style={{ background: "#3987e5", opacity: 0.3 }} /> p10–p90 band</span>
              </div>
            </div>
            <div className="panel">
              <p className="panel-title">Against the baselines</p>
              <p className="panel-sub">{forecast.data.eval.finding}</p>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>MAE €/MWh</th>
                    <th>RMSE €/MWh</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    [
                      ["lgbm_point", "LightGBM (14 features)"],
                      ["naive_yesterday", "Naive: yesterday's prices"],
                      ["seasonal_naive_7d", "Seasonal naive: last week"],
                    ] as const
                  ).map(([key, label]) => (
                    <tr key={key}>
                      <td>{label}</td>
                      <td>{forecast.data.eval.models[key].mae.toFixed(2)}</td>
                      <td>{forecast.data.eval.models[key].rmse.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <Pending what="forecast evaluation" state={forecast.state} />
        )}
      </section>

      <section className="section">
        <div className="kicker">What is the forecast worth?</div>
        <h2>Battery arbitrage backtest</h2>
        <p className="sub">
          A 1 MW / 2 MWh battery trades the day-ahead auction: charge cheap, discharge expensive,
          one cycle per day, 86% round-trip efficiency, schedules from an exact LP. Same year as
          the forecast eval. Gross revenue — no grid fees or degradation modeled.
        </p>
        {battery.state === "ready" ? (
          <>
            <div className="tile-row">
              <Tile
                label="Revenue with model forecast"
                value={fmtEur(battery.data.summary.revenue_eur.model)}
                unit="€/yr"
                good
              />
              <Tile
                label="Revenue with naive forecast"
                value={fmtEur(battery.data.summary.revenue_eur.naive)}
                unit="€/yr"
              />
              <Tile
                label="Perfect foresight (bound)"
                value={fmtEur(battery.data.summary.revenue_eur.perfect)}
                unit="€/yr"
              />
              <Tile
                label="Model edge over naive"
                value={`+${fmtEur(battery.data.summary.model_edge_over_naive_eur)}`}
                unit="€/yr"
                hint="the forecast's economic value"
                good
              />
            </div>
            <div className="panel">
              <p className="panel-title">Cumulative revenue over the eval year</p>
              <p className="panel-sub">EUR, daily day-ahead schedules evaluated at actual prices</p>
              <LineChart
                series={[
                  {
                    key: "perfect",
                    label: "Perfect foresight",
                    color: COLORS.reference,
                    values: battery.data.daily.cumulative_perfect,
                    dashed: true,
                  },
                  { key: "model", label: "Model forecast", color: COLORS.model, values: battery.data.daily.cumulative_model },
                  { key: "naive", label: "Naive forecast", color: COLORS.baseline, values: battery.data.daily.cumulative_naive },
                ]}
                xLabels={battery.data.daily.days.map((d) =>
                  new Date(d).toLocaleDateString("en-GB", { month: "short", year: "2-digit" }),
                )}
                unit="€"
                formatValue={(v) => `${Math.round(v / 1000)}k`}
              />
              <div className="legend">
                <span className="item"><span className="swatch line" style={{ background: "var(--s1)" }} /> Model forecast</span>
                <span className="item"><span className="swatch line" style={{ background: "var(--s3)" }} /> Naive forecast</span>
                <span className="item"><span className="swatch line" style={{ background: "var(--ink-2)" }} /> Perfect foresight (upper bound)</span>
              </div>
            </div>
          </>
        ) : (
          <Pending what="battery backtest" state={battery.state} />
        )}
      </section>

      <section className="section">
        <div className="kicker">Agent</div>
        <h2>A local LLM you can check the math on</h2>
        <p className="sub">
          A tool-calling agent (Ollama, runs on your machine — clone the repo, no cloud) answers
          market questions grounded in the same data. It is <em>measured</em>, not demoed: every
          answer is graded programmatically against tool output — numeric tolerance for facts,
          refusal detection for trap questions it must decline. No LLM judge.
        </p>
        {agent.state === "ready" ? (
          <>
            <div className="tile-row">
              <Tile
                label="Overall pass rate"
                value={(agent.data.pass_rate * 100).toFixed(0)}
                unit="%"
                hint={`${agent.data.n} questions · ${agent.data.model}, local`}
              />
              {Object.entries(agent.data.by_type).map(([type, s]) => (
                <Tile
                  key={type}
                  label={`${type} questions`}
                  value={`${s.passed}/${s.n}`}
                  hint={type === "trap" ? "must decline, not invent" : "graded vs tool output"}
                />
              ))}
            </div>
            <div className="panel">
              <p className="panel-title">Sample transcripts — including failures</p>
              <p className="panel-sub">curated one pass + one fail per question type</p>
              {agent.data.examples.map((ex, i) => (
                <div className="transcript" key={i}>
                  <div className="t-q">
                    <span className={`badge ${ex.passed ? "badge-pass" : "badge-fail"}`}>
                      {ex.passed ? "PASS" : "FAIL"}
                    </span>
                    <span className="t-type">{ex.type}</span> {ex.question}
                  </div>
                  <div className="t-a">{ex.answer || <em>(no final answer)</em>}</div>
                  <div className="t-meta">
                    gold: {ex.gold}
                    {ex.tools_used.length > 0 && <> · tools: {ex.tools_used.join(", ")}</>}
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : (
          <Pending what="agent evaluation" state={agent.state} />
        )}
      </section>

      <section className="section">
        <div className="kicker">Pipeline</div>
        <h2>Health</h2>
        <p className="sub">
          Every series this site renders, with its freshness. The pipeline opens a GitHub issue on
          itself when something here goes stale.
        </p>
        {health.state === "ready" ? (
          <div className="health-list">
            {Object.entries(health.data.series).map(([name, s]) => (
              <div className="health-item" key={name}>
                <span
                  className="dot"
                  style={{
                    background:
                      s.status === "ok" ? "var(--good)" : s.status === "stale" ? "var(--warning)" : "var(--critical)",
                  }}
                />
                <span>{name}</span>
                <span className="age">{s.status === "missing" ? "missing" : `${s.age_hours}h`}</span>
              </div>
            ))}
          </div>
        ) : (
          <Pending what="health report" state={health.state} />
        )}
      </section>

      <footer className="footer">
        <p>
          Data: <a href="https://www.smard.de">SMARD</a>, Bundesnetzagentur, CC BY 4.0 · hourly,
          Europe/Berlin. Built as a 0-€ pipeline: GitHub Actions + GitHub Pages, local-only LLM
          tooling. Honest by design — negative results stay in the report.
        </p>
      </footer>
    </>
  );
}

function Tile({
  label,
  value,
  unit,
  hint,
  good,
}: {
  label: string;
  value: string;
  unit?: string;
  hint?: string;
  good?: boolean;
}) {
  return (
    <div className="tile">
      <div className="label">{label}</div>
      <div className="value" style={good ? { color: "var(--good)" } : undefined}>
        {value}
        {unit && <span className="unit">{unit}</span>}
      </div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

function Pending({ what, state }: { what: string; state: "loading" | "missing" }) {
  return (
    <div className="panel">
      <p className="panel-sub" style={{ margin: 0 }}>
        {state === "loading" ? `loading ${what}…` : `${what} not produced yet — the pipeline will fill this in.`}
      </p>
    </div>
  );
}

function sumMembers(
  generation: Record<string, (number | null)[]>,
  members: string[],
): (number | null)[] {
  const present = members.filter((m) => generation[m]);
  if (!present.length) return [];
  const n = generation[present[0]].length;
  return Array.from({ length: n }, (_, i) => {
    let sum = 0;
    let any = false;
    for (const m of present) {
      const v = generation[m][i];
      if (v != null) {
        sum += v;
        any = true;
      }
    }
    return any ? sum : null;
  });
}

function fmtEur(v: number): string {
  return Math.round(v).toLocaleString("en-GB");
}
