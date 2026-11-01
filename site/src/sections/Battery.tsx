import { LineChart } from "../charts/LineChart";
import { fmtMonthYear, fmtNum, fmtPct, fmtSigned } from "../lib/format";
import { sensitivityMatrix } from "../lib/sensitivity";
import type { BatteryData, BatterySensitivity } from "../types";
import { Reveal } from "../ui";

const kFmt = (v: number) => `${Math.round(v / 1000)}k`;

export function Battery({ data }: { data: BatteryData }) {
  const s = data.summary;
  const months = data.daily.days.map(fmtMonthYear);
  return (
    <section className="band plate" id="battery" aria-label="Battery arbitrage backtest">
      <div className="wrap">
        <div className="split wide-left">
          <Reveal>
            <p className="small" style={{ marginBottom: 6 }}>
              What is the forecast worth to a battery?
            </p>
            <div className="big-figure">
              {fmtNum(s.revenue_eur.model)}
              <small>€ a year</small>
            </div>
            <h2 style={{ marginTop: 18, maxWidth: "24ch" }}>
              {fmtPct(s.capture_rate_model)} of what perfect foresight earns
            </h2>
            <p className="note" style={{ marginTop: 16 }}>
              Battery arbitrage backtest: a {s.battery.power_mw} MW / {s.battery.capacity_mwh} MWh battery trades the
              day-ahead auction, charging cheap and discharging expensive, one cycle per day, {fmtNum(
                s.battery.round_trip_efficiency * 100,
                0,
              )}
              % round-trip efficiency, schedules from an exact LP. Same year as the forecast eval. Gross revenue — no
              grid fees or degradation modeled.
            </p>
          </Reveal>
          <Reveal>
            <dl className="kv stacked">
              <dt>Revenue with the naive forecast</dt>
              <dd className="num" style={{ fontSize: 26 }}>{fmtNum(s.revenue_eur.naive)} €/yr</dd>
              <dt>Perfect foresight (upper bound)</dt>
              <dd className="num" style={{ fontSize: 26 }}>{fmtNum(s.revenue_eur.perfect)} €/yr</dd>
              <dt>Model edge over naive: the forecast&apos;s economic value</dt>
              <dd className="num" style={{ fontSize: 26, color: "var(--volt)" }}>{fmtSigned(s.model_edge_over_naive_eur)} €/yr</dd>
            </dl>
          </Reveal>
        </div>

        <Reveal className="chart-block">
          <p className="subhead" style={{ marginTop: "clamp(40px, 6vw, 72px)" }}>
            Cumulative revenue over the eval year, € (daily day-ahead schedules evaluated at actual prices)
          </p>
          <LineChart
            height={330}
            endLabels
            series={[
              { key: "perfect", label: "Perfect", color: "var(--ink-muted)", values: data.daily.cumulative_perfect, dashed: true },
              { key: "model", label: "Model", color: "var(--volt)", values: data.daily.cumulative_model, width: 3 },
              { key: "naive", label: "Naive", color: "var(--naive)", values: data.daily.cumulative_naive, width: 2 },
            ]}
            fillBetween={{ upper: "model", lower: "naive", color: "var(--volt)" }}
            xLabels={months}
            unit="€"
            formatValue={kFmt}
          />
          <div className="legend">
            <span className="item">
              <span className="swatch line" style={{ background: "var(--volt)" }} /> Model forecast
            </span>
            <span className="item">
              <span className="swatch line" style={{ background: "var(--naive)" }} /> Naive forecast
            </span>
            <span className="item">
              <span className="swatch line" style={{ background: "var(--ink-muted)" }} /> Perfect foresight (upper bound)
            </span>
            <span className="item">
              <span className="swatch" style={{ background: "var(--volt)", opacity: 0.3 }} /> The forecast&apos;s edge
            </span>
          </div>
        </Reveal>

        <Sensitivity sweep={data.sensitivity} />
      </div>
    </section>
  );
}

/* One battery is one assumption. The same LP over a small grid shows whether
   the forecast's value depends on having picked a flattering configuration. */
function Sensitivity({ sweep }: { sweep?: BatterySensitivity }) {
  const m = sweep ? sensitivityMatrix(sweep.cells) : null;
  if (!sweep || !m) return null;
  return (
    <Reveal className="split even" threshold={0.2}>
      <div className="stack" style={{ marginTop: "clamp(48px, 7vw, 88px)" }}>
        <h3>Does the edge depend on the battery?</h3>
        <p className="note">
          Same {sweep.n_days} days, same LP, only the battery changes ({sweep.power_mw} MW, one cycle per day; the
          headline battery above is 86% / 2 h).{" "}
          {m.beatsEverywhere
            ? `The model beats naive in all ${sweep.cells.length} configurations, by ${fmtNum(m.edgeMin)}–${fmtNum(m.edgeMax)} €/MW/yr.`
            : `The model does not beat naive in every configuration (edge ${fmtSigned(m.edgeMin)} to ${fmtNum(m.edgeMax)} €/MW/yr).`}
        </p>
      </div>
      <div style={{ marginTop: "clamp(48px, 7vw, 88px)" }}>
        <table className="matrix">
          <thead>
            <tr>
              <th scope="col">Round trip</th>
              {m.durations.map((d) => (
                <th scope="col" key={d}>
                  {d} h battery
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {m.efficiencies.map((e) => (
              <tr key={e}>
                <th scope="row">{Math.round(e * 100)}%</th>
                {m.durations.map((d) => {
                  const c = m.at(e, d);
                  if (!c) return <td key={d}>–</td>;
                  const edge = c.model_edge_over_naive_eur_per_mw_year;
                  return (
                    <td key={d}>
                      <span className={`edge ${edge >= 0 ? "pos" : "neg"}`}>{fmtSigned(edge)}</span>
                      <span className="sub">€/MW/yr over naive, {fmtPct(c.capture_rate_model)} of perfect</span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Reveal>
  );
}
