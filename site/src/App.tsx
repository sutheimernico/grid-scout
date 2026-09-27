import { Heatmap } from "./charts/Heatmap";
import { LineChart } from "./charts/LineChart";
import { SkillBars } from "./charts/SkillBars";
import { StackedArea } from "./charts/StackedArea";
import type { Loadable } from "./lib/useData";
import { useArtifact } from "./lib/useData";
import type {
  AgentData,
  BatteryData,
  ForecastData,
  ForwardLedgerData,
  HealthData,
  HealthEntry,
  MarketData,
  ReportEntry,
  SegmentAnalysis,
  UptimeData,
} from "./types";

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
  const ledger = useArtifact<ForwardLedgerData>("forward_ledger.json");
  const uptime = useArtifact<UptimeData>("uptime.json");

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
            {market.data.explanation && (
              <div className="panel">
                <p className="panel-title">
                  What happened on {market.data.explanation.day}
                </p>
                <p className="panel-sub" style={{ margin: 0 }}>
                  {market.data.explanation.caption}
                </p>
                <p className="panel-sub" style={{ margin: "8px 0 0", fontStyle: "italic" }}>
                  Assembled by rule from the same numbers the charts show — no model, nothing that
                  can invent a driver.
                </p>
              </div>
            )}
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
        <LiveForecast ledger={ledger} />
        {forecast.state === "ready" ? (
          <>
            <div className="panel">
              <p className="panel-title">Backtest: forecast vs. reality — last 4 weeks of the eval period</p>
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
            <Segments segments={forecast.data.segments} />
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
          Nobody operates this. GitHub Actions is the scheduler, the repo is the database, and the
          calendar below is the pipeline's own commit history — one cell per day since it went live.
        </p>
        <Uptime uptime={uptime} />
        <p className="sub" style={{ margin: "28px 0 0" }}>
          Every series this site renders, with its freshness. The pipeline opens a GitHub issue on
          itself when something here goes stale.
        </p>
        {health.state === "ready" ? (
          <>
            <div className="health-list">
              {Object.entries(health.data.series).map(([name, s]) => (
                <div className="health-item" key={name} title={s.note}>
                  <span className="dot" style={{ background: healthColor(s.status) }} />
                  <span>{name}</span>
                  <span className="age">{healthAge(s)}</span>
                </div>
              ))}
            </div>
            {health.data.reports && Object.keys(health.data.reports).length > 0 && (
              <>
                <p className="sub" style={{ margin: "20px 0 10px" }}>
                  Derived reports — the numbers above come from these. Fresh raw data says
                  nothing about whether the weekly evaluation still runs.
                </p>
                <div className="health-list">
                  {Object.entries(health.data.reports).map(([file, r]) => (
                    <div className="health-item" key={file}>
                      <span className="dot" style={{ background: reportColor(r.status) }} />
                      <span>{r.label}</span>
                      <span className="age">{reportAge(r)}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
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

/* A series SMARD stopped publishing is not a fault — it renders muted, never red,
   so the only coloured rows in this panel are ones somebody can act on. */
function healthColor(status: HealthEntry["status"]): string {
  if (status === "ok") return "var(--good)";
  if (status === "stale") return "var(--warning)";
  if (status === "discontinued") return "var(--ink-muted)";
  return "var(--critical)";
}

/* Report rows: only a report that promised a cadence and missed it turns red.
   A manual, unknown or never-produced report is muted, not an alarm. */
function reportColor(status: ReportEntry["status"]): string {
  if (status === "ok") return "var(--good)";
  if (status === "aging") return "var(--warning)";
  if (status === "overdue") return "var(--critical)";
  return "var(--ink-muted)";
}

function reportAge(r: ReportEntry): string {
  if (r.age_days == null) return r.status;
  return `${r.age_days.toFixed(0)}d`;
}

function healthAge(s: HealthEntry): string {
  if (s.status === "missing") return "missing";
  if (s.status === "discontinued") return "discontinued";
  return `${s.age_hours}h`;
}

/* The forward test: predictions written down before the auction, scored later.
   Three honest states — no ledger yet, entries still pending, entries scored. */
function LiveForecast({ ledger }: { ledger: Loadable<ForwardLedgerData> }) {
  if (ledger.state !== "ready") {
    return (
      <div className="panel">
        <p className="panel-title">Live forward test</p>
        <p className="panel-sub" style={{ margin: 0 }}>
          {ledger.state === "loading"
            ? "loading the forward ledger…"
            : "No forward ledger yet — the daily pre-auction run starts it. Everything below is the backtest."}
        </p>
      </div>
    );
  }
  const { summary, latest, method } = ledger.data;
  const cum = summary.cumulative;
  const week = summary.last_7_days;

  return (
    <div className="panel">
      <p className="panel-title">Live forward test — predictions made before the auction</p>
      <p className="panel-sub">{method}</p>
      <div className="tile-row">
        <Tile
          label="Forecasts recorded"
          value={String(summary.n_records)}
          hint={
            summary.first_target_date
              ? `since ${summary.first_target_date} · ${summary.n_pending} awaiting their prices`
              : "none yet"
          }
        />
        <Tile
          label="Scored days"
          value={String(summary.n_scored)}
          hint={cum ? `${cum.n_hours} delivered hours` : "first scores arrive a day after the first forecast"}
        />
        {cum && (
          <>
            <Tile label="MAE model (cumulative)" value={cum.mae_model.toFixed(2)} unit="€/MWh" />
            <Tile
              label="MAE naive (cumulative)"
              value={cum.mae_naive.toFixed(2)}
              unit="€/MWh"
              hint={`model beat naive on ${cum.days_model_beat_naive}/${cum.n_days} days`}
            />
            {week && (
              <Tile
                label="Last 7 days"
                value={`${week.mae_model.toFixed(1)} / ${week.mae_naive.toFixed(1)}`}
                unit="€/MWh"
                hint="model / naive"
              />
            )}
          </>
        )}
      </div>
      {cum == null && (
        <p className="panel-sub" style={{ marginTop: 12 }}>
          No scored day yet. Nothing here is claimed until the cleared prices arrive — that is the
          whole point of a forward test.
        </p>
      )}
      {latest && (
        <>
          <p className="panel-sub" style={{ marginTop: 16 }}>
            Delivery day {latest.target_date}, predicted{" "}
            {new Date(latest.generated_at_utc).toLocaleString("en-GB", {
              timeZone: "Europe/Berlin",
            })}
            {latest.scored ? " · cleared prices overlaid" : " · outcome still open"}
          </p>
          <LineChart
            series={[
              ...(latest.actual
                ? [
                    {
                      key: "actual",
                      label: "Cleared price",
                      color: COLORS.model,
                      values: latest.actual as (number | null)[],
                    },
                  ]
                : []),
              {
                key: "pred",
                label: "Pre-auction forecast",
                color: COLORS.baseline,
                values: latest.pred_model as (number | null)[],
              },
              {
                key: "naive",
                label: "Naive baseline",
                color: COLORS.reference,
                values: latest.pred_naive as (number | null)[],
                dashed: true,
              },
            ]}
            xLabels={latest.hours_local.map((h) => `${String(h).padStart(2, "0")}:00`)}
            unit="€/MWh"
            xTickEvery={3}
          />
          <div className="legend">
            {latest.actual && (
              <span className="item">
                <span className="swatch line" style={{ background: COLORS.model }} /> Cleared price
              </span>
            )}
            <span className="item">
              <span className="swatch line" style={{ background: COLORS.baseline }} /> Pre-auction
              forecast
            </span>
            <span className="item">
              <span className="swatch line" style={{ background: COLORS.reference }} /> Naive
              baseline
            </span>
          </div>
        </>
      )}
    </div>
  );
}

/* Aggregate MAE hides the interesting part. Segments where a naive baseline
   still wins stay in the picture instead of being filtered out. */
function Segments({ segments }: { segments?: SegmentAnalysis }) {
  if (!segments) return null;
  const slices = [...segments.by_hour, ...segments.by_weekday, ...segments.by_regime];
  const losing = slices.filter((s) => s.best !== "model");
  // Named from the data, never from a sentence written once: the weekly re-eval
  // moves these numbers, and a stale claim here would be the dishonest kind.
  const weakest = slices
    .filter((s) => s.skill_vs_naive_pct != null)
    .sort((a, b) => a.skill_vs_naive_pct! - b.skill_vs_naive_pct!)
    .slice(0, 2)
    .map((s) => `${s.segment} (${s.skill_vs_naive_pct!.toFixed(1)}%)`);
  return (
    <div className="panel">
      <p className="panel-title">Where the model wins — and where it does not</p>
      <p className="panel-sub">
        Skill against the naive baseline per slice of the same {segments.n_hours.toLocaleString("en-GB")}{" "}
        out-of-sample hours. Above zero the model wins, below zero the baseline does.{" "}
        {losing.length === 0
          ? `No slice where a baseline beats the model in this eval period${
              weakest.length ? ` — the weakest are ${weakest.join(" and ")}` : ""
            }.`
          : `A baseline still beats the model in: ${losing.map((s) => s.segment).join(", ")}.`}
      </p>
      <p className="panel-sub" style={{ marginBottom: 4 }}>By hour of day</p>
      <SkillBars segments={segments.by_hour} label="Forecast skill by hour of day" labelEvery={2} />
      <p className="panel-sub" style={{ margin: "14px 0 4px" }}>By weekday</p>
      <SkillBars segments={segments.by_weekday} label="Forecast skill by weekday" height={140} />
      <p className="panel-sub" style={{ margin: "14px 0 4px" }}>By price regime</p>
      <table className="data-table">
        <thead>
          <tr>
            <th>Regime</th>
            <th>Hours</th>
            <th>MAE model</th>
            <th>MAE naive</th>
            <th>Skill</th>
          </tr>
        </thead>
        <tbody>
          {segments.by_regime.map((s) => (
            <tr key={s.segment}>
              <td title={segments.definitions[s.segment]}>{s.segment}</td>
              <td>{s.n.toLocaleString("en-GB")}</td>
              <td>{s.mae_model.toFixed(2)}</td>
              <td>{s.mae_naive.toFixed(2)}</td>
              <td style={{ color: (s.skill_vs_naive_pct ?? 0) >= 0 ? "var(--good)" : "var(--critical)" }}>
                {s.skill_vs_naive_pct == null ? "–" : `${s.skill_vs_naive_pct.toFixed(1)}%`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Uptime({ uptime }: { uptime: Loadable<UptimeData> }) {
  if (uptime.state !== "ready") {
    return <Pending what="uptime calendar" state={uptime.state} />;
  }
  const { days, totals, reference_runs_per_day, scheduled_runs_per_day, first_day } = uptime.data;
  return (
    <div className="panel">
      <p className="panel-title">
        {totals.days} days live · {totals.runs} published refreshes ·{" "}
        {totals.days_with_zero_runs === 0
          ? "no silent day"
          : `${totals.days_with_zero_runs} silent days (longest streak ${totals.longest_silent_streak_days})`}
      </p>
      <p className="panel-sub">
        Since {first_day}. A cell counts refreshes the pipeline actually published that day; a run
        that finds no new SMARD data commits nothing, so a pale cell is a quiet market, not an
        outage. {scheduled_runs_per_day} cron slots per day, median {reference_runs_per_day}{" "}
        published.
      </p>
      <Heatmap
        days={days}
        expectedPerDay={reference_runs_per_day}
        label={`Pipeline runs per day since ${first_day}`}
      />
    </div>
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

export function sumMembers(
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
