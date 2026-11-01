import { LineChart } from "../charts/LineChart";
import { StackedArea } from "../charts/StackedArea";
import { fmtDateTime, fmtDay, fmtNum, fmtPct, unitSpelling } from "../lib/format";
import type { MarketData } from "../types";
import { Reveal } from "../ui";

/* Generation mix: 11 raw series folded to 6 groups, fixed entity-to-colour
   mapping, stack order bottom = steady, top = volatile. */
const GEN_GROUPS: { key: string; label: string; color: string; members: string[] }[] = [
  { key: "other_conv", label: "Other conventional", color: "#8f9794", members: ["gen_other_conventional", "gen_pumped_storage", "gen_nuclear"] },
  { key: "coal", label: "Coal", color: "#3b4442", members: ["gen_lignite", "gen_hard_coal"] },
  { key: "gas", label: "Natural gas", color: "#c9722a", members: ["gen_gas"] },
  { key: "other_renew", label: "Hydro, biomass & other renewables", color: "#5f9a4d", members: ["gen_hydro", "gen_biomass", "gen_other_renewable"] },
  { key: "wind", label: "Wind (on- + offshore)", color: "#1f8a9e", members: ["gen_wind_onshore", "gen_wind_offshore"] },
  { key: "solar", label: "Solar", color: "#e0a100", members: ["gen_solar"] },
];

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

export function Market({ data }: { data: MarketData }) {
  const k = data.kpis;
  const labels = data.hourly.timestamps.map((t) => fmtDay(t));
  return (
    <section className="band" id="market" aria-label="The German market">
      <div className="wrap">
        <div className="split even" style={{ alignItems: "end" }}>
          <Reveal>
            <h2>The last 14 days on the German grid</h2>
          </Reveal>
          <Reveal>
            <p className="note">
              Day-ahead auction prices and the generation mix behind them. Price valleys line up with solar peaks;
              negative prices happen when renewables flood the market.
            </p>
          </Reveal>
        </div>
        <Reveal className="kpis" threshold={0.3}>
          <div className="kpi">
            <b>
              {fmtNum(k.latest_price_eur_mwh, 2)}
              <small>€/MWh</small>
            </b>
            <span>latest day-ahead price, {fmtDateTime(k.latest_price_at)} Berlin time</span>
          </div>
          <div className="kpi">
            <b>{fmtNum(k.negative_price_hours_ytd)}</b>
            <span>hours below 0 €/MWh this year</span>
          </div>
          <div className="kpi">
            <b>{fmtPct(k.renewables_share_last_24h, 0)}</b>
            <span>renewables, of measured generation (24 h)</span>
          </div>
        </Reveal>

        <Reveal className="chart-block">
          <p className="subhead" style={{ marginTop: "clamp(36px, 5vw, 56px)" }}>
            Day-ahead price, €/MWh, hourly, Europe/Berlin. Hours below zero are drawn in red.
          </p>
          <div className="chart-plate">
            <LineChart
              height={250}
              series={[{ key: "price", label: "Day-ahead price", color: "var(--c-actual)", values: data.hourly.price, width: 1.6 }]}
              negativeColor="var(--neg)"
              xLabels={labels}
              unit="€/MWh"
            />
          </div>
        </Reveal>

        <div className="split wide-left" style={{ marginTop: "clamp(36px, 5vw, 56px)" }}>
          <Reveal>
            <p className="subhead" style={{ marginTop: 0 }}>
              Generation mix, GWh per hour, measured, grouped from 11 SMARD series
            </p>
            <div className="chart-plate">
              <StackedArea
                height={290}
                series={GEN_GROUPS.map((g) => ({
                  key: g.key,
                  label: g.label,
                  color: g.color,
                  values: sumMembers(data.hourly.generation, g.members),
                }))}
                xLabels={labels}
                unit="MWh"
                formatValue={(v) => `${Math.round(v / 1000)}`}
              />
            </div>
            <div className="legend">
              {[...GEN_GROUPS].reverse().map((g) => (
                <span className="item" key={g.key}>
                  <span className="swatch" style={{ background: g.color }} /> {g.label}
                </span>
              ))}
            </div>
          </Reveal>
          {data.explanation && (
            <Reveal className="stack">
              <p className="happened-label">What happened on {data.explanation.day}</p>
              <p className="happened">{unitSpelling(data.explanation.caption)}</p>
              <p className="small">
                Assembled by rule from the same numbers the charts show — no model, nothing that can invent a driver.
              </p>
            </Reveal>
          )}
        </div>
      </div>
    </section>
  );
}
