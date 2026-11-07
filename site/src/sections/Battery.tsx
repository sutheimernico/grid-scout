import { LineChart } from "../charts/LineChart";
import { fmtMonthYear, fmtNum, fmtPct, fmtSigned } from "../lib/format";
import { revenueSplit, splitWidths, type RevenueSplit } from "../lib/battery";
import { sensitivityMatrix } from "../lib/sensitivity";
import type { BatteryData, BatterySensitivity } from "../types";
import { Reveal } from "../ui";

const kFmt = (v: number) => `${Math.round(v / 1000)}k`;

export function Battery({ data }: { data: BatteryData }) {
  const s = data.summary;
  const split = revenueSplit(s);
  const months = data.daily.days.map(fmtMonthYear);
  return (
    <section className="band plate" id="battery" aria-label="Battery arbitrage backtest">
      <div className="wrap">
        <div className="split wide-left">
          <Reveal>
            <p className="small" style={{ marginBottom: 6 }}>
              What the forecast adds to a {s.battery.power_mw} MW / {s.battery.capacity_mwh} MWh battery
              {split.edgePct != null ? `: ${fmtSigned(split.edgePct, 1)}% over a naive forecast` : ""}
            </p>
            <div className="big-figure">
              {fmtSigned(split.edge)}
              <small>€ a year</small>
            </div>
            <p className="small" style={{ marginTop: 10 }}>
              Full model: assumes the TSOs&apos; generation forecast for the delivery day is known.
            </p>
            <h2 style={{ marginTop: 18, maxWidth: "26ch" }}>
              Most of the revenue is the battery, not the forecast
            </h2>
            <p className="note" style={{ marginTop: 16 }}>
              Even the naive forecast earns {fmtNum(split.naive)} € a year, because a battery that charges at night and
              discharges in the evening captures most of the daily spread. The forecast's value is the difference to
              that: {fmtSigned(split.edge)} €, and {fmtPct(s.capture_rate_model)} of perfect foresight instead of{" "}
              {fmtPct(s.capture_rate_naive)}. One cycle per day, {fmtNum(s.battery.round_trip_efficiency * 100, 0)}%
              round-trip efficiency, schedules from an exact LP, same year as the forecast eval. Gross revenue, no grid
              fees or degradation. The schedules use the full model's forecasts (TSO generation forecast assumed
              known); this backtest has not been re-run on pre-auction forecasts.
            </p>
          </Reveal>
          <Reveal>
            <RevenueBar split={split} />
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

/* One bar, scaled to perfect foresight and starting at zero: what any forecast
   earns, what this forecast adds, what is still on the table. */
function RevenueBar({ split }: { split: RevenueSplit }) {
  const w = splitWidths(split);
  return (
    <div className="revbar" role="img" aria-label={`Revenue per year: naive ${fmtNum(split.naive)} euro, model adds ${fmtSigned(split.edge)}, ${fmtNum(split.gap)} short of perfect foresight`}>
      <div className="revbar-track">
        <i className="seg naive grow-x" style={{ width: `${w.naive}%` }} />
        <i className="seg edge grow-x" style={{ width: `${w.edge}%`, left: `${w.naive}%`, ["--delay" as string]: "250ms" }} />
        <i className="seg gap grow-x" style={{ width: `${w.gap}%`, left: `${w.naive + w.edge}%`, ["--delay" as string]: "450ms" }} />
      </div>
      <ul className="revbar-key">
        <li>
          <i className="sw naive" />
          <b>{fmtNum(split.naive)} €</b>
          <span>naive forecast: yesterday&apos;s prices</span>
        </li>
        <li>
          <i className="sw edge" />
          <b style={{ color: "var(--volt)" }}>{fmtSigned(split.edge)} €</b>
          <span>added by the model forecast</span>
        </li>
        <li>
          <i className="sw gap" />
          <b>{fmtNum(split.gap)} €</b>
          <span>still missing to perfect foresight ({fmtNum(split.perfect)} €)</span>
        </li>
      </ul>
    </div>
  );
}
