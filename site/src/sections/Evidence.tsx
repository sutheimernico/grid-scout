import { Calibration } from "../charts/Calibration";
import { Scoreboard } from "../charts/Scoreboard";
import { SkillBars } from "../charts/SkillBars";
import { fmtNum, fmtSigned, unitSpelling } from "../lib/format";
import { buildScoreboard } from "../lib/scoreboard";
import { losingSlices, segmentExtremes } from "../lib/segments";
import type { ForecastData, SegmentAnalysis } from "../types";
import { Reveal } from "../ui";

export function Evidence({ data }: { data: ForecastData }) {
  const { eval: ev } = data;
  const rows = buildScoreboard(ev);
  const q = ev.quantiles;
  const pre = ev.pre_auction;
  return (
    <section className="band plate" id="forecast" aria-label="Forecast accuracy">
      <div className="wrap">
        <div className="split">
          <Reveal className="stack">
            <h2>
              {pre
                ? `${fmtNum(pre.skill_vs_naive_pct, 1)}% less error than yesterday's prices, on public pre-auction data`
                : `${fmtNum(ev.skill.lgbm_vs_naive_pct, 1)}% less error than copying yesterday's prices`}
            </h2>
            <p className="note">
              {pre
                ? `Two models, two answers: ${fmtNum(pre.skill_vs_naive_pct, 1)}% with inputs published before the auction, ${fmtNum(ev.skill.lgbm_vs_naive_pct, 1)}% when the TSOs' generation forecast for the delivery day is assumed known, as it is for a trader with TSO feeds. `
                : ""}
              The hero chart, the band, the hour and weekday slices and the battery backtest below all use the second,
              full model; the battery backtest has not been re-run on pre-auction forecasts. Every number is
              out-of-sample: expanding walk-forward over a full year, refit weekly.
            </p>
            <p className="note">{unitSpelling(ev.finding)}</p>
          </Reveal>
          <Reveal>
            <Scoreboard rows={rows} />
          </Reveal>
        </div>

        <Reveal className="split even" threshold={0.2}>
          <div className="stack" style={{ marginTop: "clamp(48px, 7vw, 88px)" }}>
            <h3>An honest band, not a promised one</h3>
            <p className="note">
              The p10 to p90 band should hold the real price 80% of the time. The raw quantile model holds it{" "}
              {fmtNum(q.coverage_p10_p90 * 100, 0)}% of the time, too narrow
              {q.conformal
                ? `; walk-forward conformal calibration widens it${
                    q.conformal.mean_width_raw != null
                      ? ` from ${fmtNum(q.conformal.mean_width_raw, 0)} to ${fmtNum(q.conformal.mean_width_calibrated, 0)} €/MWh on average`
                      : ""
                  } and reaches ${fmtNum(q.conformal.coverage_p10_p90 * 100, 0)}%`
                : ""}
              .
            </p>
          </div>
          <div style={{ marginTop: "clamp(48px, 7vw, 88px)" }}>
            <Calibration raw={q.coverage_p10_p90} calibrated={q.conformal?.coverage_p10_p90} target={q.target_coverage} />
          </div>
        </Reveal>
      </div>
    </section>
  );
}

export function Segments({ segments }: { segments?: SegmentAnalysis }) {
  if (!segments) return null;
  const slices = [...segments.by_hour, ...segments.by_weekday, ...segments.by_regime];
  const losing = losingSlices(slices);
  // Named from the data, never from a sentence written once: the weekly re-eval
  // moves these numbers, and a stale claim here would be the dishonest kind.
  const weakest = slices
    .filter((s) => s.skill_vs_naive_pct != null)
    .sort((a, b) => a.skill_vs_naive_pct! - b.skill_vs_naive_pct!)
    .slice(0, 2)
    .map((s) => `${s.segment} (${s.skill_vs_naive_pct!.toFixed(1)}%)`);
  const { best, worst } = segmentExtremes(segments.by_hour);

  return (
    <section className="band" aria-label="Forecast skill by slice">
      <div className="wrap">
        <div className="split wide-left">
          <Reveal>
            <h2 style={{ maxWidth: "20ch" }}>
              {best && worst
                ? `Strongest at ${best.segment}, weakest at ${worst.segment}`
                : "Where the model wins and where it does not"}
            </h2>
            <p className="note" style={{ marginTop: 18 }}>
              Where the model wins — and where it does not. Full model, skill against the naive baseline per slice of the same{" "}
              {fmtNum(segments.n_hours)} out-of-sample hours. Above zero the model wins, below zero the baseline does.{" "}
              {losing.length === 0
                ? `No slice where a baseline beats the model in this eval period${
                    weakest.length ? ` — the weakest are ${weakest.join(" and ")}` : ""
                  }.`
                : `A baseline still beats the model in: ${losing.map((s) => s.segment).join(", ")}.`}
            </p>
            <p className="subhead">By hour of day (Europe/Berlin)</p>
            <SkillBars segments={segments.by_hour} label="Forecast skill by hour of day" labelEvery={3} />
          </Reveal>
          <Reveal>
            <p className="subhead" style={{ marginTop: 0 }}>By weekday</p>
            <SkillBars segments={segments.by_weekday} label="Forecast skill by weekday" height={150} showValues />
            <p className="subhead">By price regime</p>
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
                    <td title={unitSpelling(segments.definitions[s.segment] ?? "")}>{s.segment}</td>
                    <td>{fmtNum(s.n)}</td>
                    <td>{fmtNum(s.mae_model, 2)}</td>
                    <td>{fmtNum(s.mae_naive, 2)}</td>
                    <td className={(s.skill_vs_naive_pct ?? 0) >= 0 ? "pos" : "neg"}>
                      {s.skill_vs_naive_pct == null ? "–" : `${fmtSigned(s.skill_vs_naive_pct, 1)}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="note" style={{ margin: "18px 0 0" }}>
              {segments.by_regime.map((s) =>
                segments.definitions[s.segment] ? (
                  <div key={s.segment} style={{ marginBottom: 6 }}>
                    <b>{s.segment}:</b> {unitSpelling(segments.definitions[s.segment])}
                  </div>
                ) : null,
              )}
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
