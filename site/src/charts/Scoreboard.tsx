import type { ScoreRow } from "../lib/scoreboard";
import { rulerMax } from "../lib/scoreboard";
import { fmtSigned } from "../lib/format";
import { CountUp } from "../ui";
import { useInView } from "../lib/motion";

/** One horizontal scale in EUR/MWh with every model on it. The distance between
 *  bars is the point, so the scale starts at zero and the bars are not truncated. */
export function Scoreboard({ rows }: { rows: ScoreRow[] }) {
  const [ref, seen] = useInView<HTMLDivElement>(0.2);
  const max = rulerMax(rows);
  const marks = Array.from({ length: max / 10 + 1 }, (_, i) => i * 10);
  const pct = (v: number) => `${(v / max) * 100}%`;
  const lastModel = rows.length - 1;

  return (
    <div className={`ruler ${seen ? "is-in" : ""}`} ref={ref} role="table" aria-label="Mean absolute error per model, EUR per MWh, lower is better">
      <div className="ruler-scale" aria-hidden="true">
        {marks.map((m) => (
          <span key={m} style={{ left: pct(m) }}>
            {m}
            {m === 0 ? " €/MWh" : ""}
          </span>
        ))}
      </div>
      {rows.map((r, i) => {
        const isHero = i === lastModel && r.kind === "model";
        return (
          <div className={`ruler-row ${r.kind} ${isHero ? "hero-row" : ""}`} key={r.key} role="row">
            <div className="name" role="rowheader">
              <span>
                {r.label}
                <small>{r.detail}</small>
              </span>
              {r.skillVsNaive != null && r.key !== "naive_yesterday" && (
                <span className={`chip ${r.skillVsNaive > 0 ? "up" : ""}`}>
                  {fmtSigned(r.skillVsNaive, 1)}% vs yesterday
                </span>
              )}
            </div>
            <div className="ruler-track" role="cell">
              {marks.map((m) => (
                <i className="tick" key={m} style={{ left: pct(m) }} />
              ))}
              <i
                className="bar grow-x"
                style={{ width: pct(r.mae), ["--delay" as string]: `${i * 80}ms` }}
              />
              <span className="value" style={{ left: pct(r.mae) }}>
                <CountUp value={r.mae} digits={2} active={seen} delayMs={i * 80} />
              </span>
            </div>
          </div>
        );
      })}
      <p className="ruler-caption">
        Mean absolute error in €/MWh, out-of-sample; lower is better. The bars start at zero.
      </p>
    </div>
  );
}
