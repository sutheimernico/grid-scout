import { useCallback, useMemo, useRef, useState } from "react";
import { bandPath, linePath, linearScale, ticks } from "./scale";
import { useChartWidth } from "../lib/useChartWidth";
import { fmtHourLabel, fmtNum, fmtSigned, localParts } from "../lib/format";
import type { HeroWindow } from "../lib/hero";
import { useInView } from "../lib/motion";

const MARGIN = { top: 30, right: 14, bottom: 28, left: 46 };

/** The hero: forecast, band and cleared prices for the last complete delivery
 *  days of the backtest. Hover or arrow keys move a crosshair; the values appear
 *  in the readout row above the plot so nothing floats over the curves. */
export function HeroChart({ window: w, height = 380 }: { window: HeroWindow; height?: number }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const WIDTH = useChartWidth(wrapRef, 1240);
  const [hover, setHover] = useState<number | null>(null);
  const [rootRef, seen] = useInView<HTMLDivElement>(0.25);
  const n = w.timestamps.length;
  const innerW = WIDTH - MARGIN.left - MARGIN.right;
  const innerH = height - MARGIN.top - MARGIN.bottom;

  const { x, y, yTicks } = useMemo(() => {
    const vals = [...w.actual, ...w.predicted, ...w.q10, ...w.q90].filter((v): v is number => v != null);
    const lo = Math.min(0, ...vals);
    const hi = Math.max(...vals, 10);
    const pad = (hi - lo) * 0.06;
    const y = linearScale([lo - (lo < 0 ? pad : 0), hi + pad], [MARGIN.top + innerH, MARGIN.top]);
    // each hour owns one column; points sit at the column centre
    const col = innerW / n;
    const x = (i: number) => MARGIN.left + (i + 0.5) * col;
    return { x, y, yTicks: ticks([lo, hi + pad], 5) };
  }, [w, n, innerW, innerH]);

  const col = innerW / n;
  const hours = useMemo(() => w.timestamps.map((t) => localParts(t)), [w.timestamps]);
  const compact = WIDTH < 560;
  const labelEvery = compact ? 12 : 6;

  const indexAt = useCallback(
    (clientX: number, rect: DOMRect) => {
      const px = ((clientX - rect.left) / rect.width) * WIDTH;
      const i = Math.floor((px - MARGIN.left) / col);
      return i >= 0 && i < n ? i : null;
    },
    [WIDTH, col, n],
  );

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowRight") setHover((h) => Math.min(n - 1, (h ?? -1) + 1));
    else if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? n) - 1));
    else if (e.key === "Escape") setHover(null);
    else return;
    e.preventDefault();
  }

  const h = hover;
  const actualAt = h != null ? w.actual[h] : null;
  const predAt = h != null ? w.predicted[h] : null;
  const lo = h != null ? w.q10[h] : null;
  const hi = h != null ? w.q90[h] : null;

  return (
    <div className={`hero-chart ${seen ? "is-in" : ""}`} ref={rootRef}>
      <div className="readout" aria-live="polite">
        {h == null ? (
          <>
            <span className="key">
              <i className="sw" /> Cleared price
            </span>
            <span className="key">
              <i className="sw model" /> Forecast
            </span>
            <span className="key">
              <i className="sw bandkey" /> p10 to p90 band
            </span>
            {w.negativeSpans.length > 0 && (
              <span className="key">
                <i className="sw negcol" /> Hours below 0
              </span>
            )}
            <span className="grow small">
              {w.stats.nHours} hours
              {w.stats.mae != null && <> · MAE {fmtNum(w.stats.mae, 1)} €/MWh</>}
              {w.stats.coverage != null && <> · {fmtNum(w.stats.coverage * 100, 0)}% inside the band</>}
            </span>
          </>
        ) : (
          <>
            <span className="when">
              {hours[h].dayLabel}, {fmtHourLabel(hours[h].hour)}
            </span>
            <span className="val">
              Cleared <b>{actualAt == null ? "–" : `${fmtSigned(actualAt, 1)} €/MWh`}</b>
            </span>
            <span className="val" style={{ color: "var(--volt)" }}>
              Forecast <b style={{ color: "var(--volt)" }}>{predAt == null ? "–" : `${fmtSigned(predAt, 1)} €/MWh`}</b>
            </span>
            <span className="val">
              Band <b>{lo == null || hi == null ? "–" : `${fmtNum(lo, 0)} to ${fmtNum(hi, 0)}`}</b>
            </span>
            {actualAt != null && predAt != null && (
              <span className="val">
                Error <b>{fmtSigned(predAt - actualAt, 1)}</b>
              </span>
            )}
          </>
        )}
      </div>

      <div className="chart-plate">
        <div className="chart-wrap" ref={wrapRef}>
          <svg
            viewBox={`0 0 ${WIDTH} ${height}`}
            width="100%"
            role="img"
            tabIndex={0}
            aria-label={`Day-ahead forecast against cleared prices for ${w.days.map((d) => d.label).join(", ")}. Arrow keys move through the hours.`}
            onMouseMove={(e) => setHover(indexAt(e.clientX, e.currentTarget.getBoundingClientRect()))}
            onMouseLeave={() => setHover(null)}
            onTouchMove={(e) => setHover(indexAt(e.touches[0].clientX, e.currentTarget.getBoundingClientRect()))}
            onKeyDown={onKey}
            onBlur={() => setHover(null)}
          >
            {/* alternate day bands; the label names the delivery day */}
            {w.days.map((d, di) => (
              <g key={d.date}>
                {di % 2 === 1 && (
                  <rect
                    x={MARGIN.left + d.from * col}
                    y={MARGIN.top}
                    width={(d.to - d.from) * col}
                    height={innerH}
                    fill="var(--tint)"
                    opacity={0.55}
                  />
                )}
                <text className="day-label" x={MARGIN.left + d.from * col + 8} y={MARGIN.top - 12}>
                  {d.label}
                </text>
              </g>
            ))}

            {w.negativeSpans.map(([a, b]) => (
              <rect
                key={`${a}-${b}`}
                x={MARGIN.left + a * col}
                y={MARGIN.top}
                width={(b - a) * col}
                height={innerH}
                fill="var(--neg)"
                opacity={0.11}
              />
            ))}

            {yTicks.map((t) => (
              <g key={t}>
                <line
                  x1={MARGIN.left}
                  x2={WIDTH - MARGIN.right}
                  y1={y(t)}
                  y2={y(t)}
                  stroke={t === 0 ? "var(--ink)" : "var(--c-grid)"}
                  strokeWidth={t === 0 ? 1.25 : 1}
                />
                <text x={MARGIN.left - 8} y={y(t) + 4} textAnchor="end">
                  {fmtNum(t)}
                </text>
              </g>
            ))}
            <text x={MARGIN.left - 8} y={MARGIN.top - 12} textAnchor="end">
              €/MWh
            </text>

            {hours.map((p, i) =>
              p.hour % labelEvery === 0 ? (
                <text key={i} x={x(i)} y={height - 8} textAnchor="middle">
                  {fmtHourLabel(p.hour)}
                </text>
              ) : null,
            )}
            {w.days.slice(1).map((d) => (
              <line
                key={d.date}
                x1={MARGIN.left + d.from * col}
                x2={MARGIN.left + d.from * col}
                y1={MARGIN.top}
                y2={MARGIN.top + innerH + 6}
                stroke="var(--c-axis)"
                strokeWidth={1}
              />
            ))}

            <g className="wipe" style={{ ["--delay" as string]: "0ms" }}>
              <path d={bandPath(w.q90, w.q10, x, y)} fill="var(--volt)" opacity={0.14} />
            </g>
            <path
              className="draw"
              pathLength={1}
              d={linePath(w.actual, x, y)}
              fill="none"
              stroke="var(--c-actual)"
              strokeWidth={1.75}
              strokeLinejoin="round"
              style={{ ["--delay" as string]: "450ms" }}
            />
            <path
              className="draw"
              pathLength={1}
              d={linePath(w.predicted, x, y)}
              fill="none"
              stroke="var(--c-model)"
              strokeWidth={2.75}
              strokeLinejoin="round"
              strokeLinecap="round"
              style={{ ["--delay" as string]: "150ms" }}
            />

            {h != null && (
              <g className="noise-free">
                <line x1={x(h)} x2={x(h)} y1={MARGIN.top} y2={MARGIN.top + innerH} stroke="var(--ink)" strokeWidth={1} />
                {actualAt != null && <circle cx={x(h)} cy={y(actualAt)} r={4.5} fill="var(--ink)" stroke="#fff" strokeWidth={2} />}
                {predAt != null && <circle cx={x(h)} cy={y(predAt)} r={5} fill="var(--volt)" stroke="#fff" strokeWidth={2} />}
              </g>
            )}
          </svg>
        </div>
      </div>
    </div>
  );
}
