import { useId, useMemo, useRef, useState } from "react";
import { bandPath, extent, linePath, linearScale, spreadLabels, ticks } from "./scale";
import { useChartWidth } from "../lib/useChartWidth";

export interface LineSeries {
  key: string;
  label: string;
  color: string;
  values: (number | null)[];
  dashed?: boolean;
  width?: number;
}

interface Props {
  series: LineSeries[];
  xLabels: string[]; // one per index, preformatted
  height?: number;
  unit: string;
  formatValue?: (v: number) => string;
  xTickEvery?: number;
  /** label each series at its last point, in its own colour (needs room on the right) */
  endLabels?: boolean;
  /** fill between two series (upper first) to show what separates them */
  fillBetween?: { upper: string; lower: string; color: string };
  /** paint the part of every line below zero in this colour */
  negativeColor?: string;
}

/** Multi-series line chart: hairline grid, zero baseline, gap-aware lines,
 *  crosshair + tooltip on hover. Draws in once when its parent gets `.is-in`. */
export function LineChart({
  series,
  xLabels,
  height = 260,
  unit,
  formatValue = (v) => v.toFixed(0),
  xTickEvery,
  endLabels = false,
  fillBetween,
  negativeColor,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const WIDTH = useChartWidth(wrapRef);
  const [hover, setHover] = useState<number | null>(null);
  const clipId = useId().replace(/:/g, "");

  const margin = { top: 14, right: endLabels ? (WIDTH < 560 ? 64 : 104) : 14, bottom: 28, left: 46 };
  const n = xLabels.length;
  const innerW = WIDTH - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const { y, yTicks, x } = useMemo(() => {
    let [lo, hi] = extent(series.map((s) => s.values));
    lo = Math.min(lo, 0);
    const pad = (hi - lo) * 0.06;
    const floor = lo < 0 ? lo - pad : lo;
    const y = linearScale([floor, hi + pad], [margin.top + innerH, margin.top]);
    const x = (i: number) => margin.left + (n <= 1 ? 0 : (i / (n - 1)) * innerW);
    return { y, yTicks: ticks([floor, hi + pad], 5), x };
  }, [series, n, innerH, innerW, margin.top, margin.left]);

  const step = xTickEvery ?? Math.max(1, Math.round(n / Math.max(2, Math.min(7, Math.floor(WIDTH / 120)))));
  const xTickIdx = Array.from({ length: n }, (_, i) => i).filter((i) => i % step === 0);

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * WIDTH;
    const i = Math.round(((px - margin.left) / innerW) * (n - 1));
    setHover(i >= 0 && i < n ? i : null);
  }

  const tooltipLeft = hover != null && wrapRef.current ? (x(hover) / WIDTH) * wrapRef.current.clientWidth : 0;
  const byKey = (k: string) => series.find((s) => s.key === k);
  const fill = fillBetween && byKey(fillBetween.upper) && byKey(fillBetween.lower) ? fillBetween : undefined;
  const zeroY = y(0);

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        width="100%"
        role="img"
        aria-label={`Line chart, ${series.map((s) => s.label).join(", ")}, in ${unit}`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <clipPath id={`neg-${clipId}`}>
            <rect x={margin.left} y={zeroY} width={innerW} height={Math.max(0, margin.top + innerH - zeroY + 2)} />
          </clipPath>
        </defs>
        {yTicks.map((t) => (
          <g key={t}>
            <line
              x1={margin.left}
              x2={WIDTH - margin.right}
              y1={y(t)}
              y2={y(t)}
              stroke={t === 0 ? "var(--c-axis)" : "var(--c-grid)"}
              strokeWidth={1}
            />
            <text x={margin.left - 8} y={y(t) + 4} textAnchor="end">
              {formatValue(t)}
            </text>
          </g>
        ))}
        {xTickIdx.map((i) => (
          <text key={i} x={x(i)} y={height - 8} textAnchor="middle">
            {xLabels[i]}
          </text>
        ))}

        {fill && (
          <g className="wipe">
            <path
              d={bandPath(byKey(fill.upper)!.values, byKey(fill.lower)!.values, x, y)}
              fill={fill.color}
              opacity={0.16}
            />
          </g>
        )}

        {series.map((s, si) => {
          const d = linePath(s.values, x, y);
          const common = {
            d,
            fill: "none",
            strokeWidth: s.width ?? 2,
            strokeDasharray: s.dashed ? "5 5" : undefined,
            strokeLinejoin: "round" as const,
            strokeLinecap: "round" as const,
          };
          return (
            <g key={s.key}>
              {s.dashed ? (
                <path {...common} stroke={s.color} className="fade-in" style={{ ["--delay" as string]: `${si * 120}ms` }} />
              ) : (
                <path
                  {...common}
                  stroke={s.color}
                  pathLength={1}
                  className="draw"
                  style={{ ["--delay" as string]: `${si * 140}ms` }}
                />
              )}
              {negativeColor && <path {...common} stroke={negativeColor} clipPath={`url(#neg-${clipId})`} />}
            </g>
          );
        })}

        {endLabels &&
          (() => {
            const ends = series
              .map((s) => {
                let last = -1;
                for (let i = s.values.length - 1; i >= 0; i--)
                  if (s.values[i] != null) {
                    last = i;
                    break;
                  }
                return last < 0 ? null : { s, last, y: y(s.values[last]!) + 4 };
              })
              .filter((e): e is { s: LineSeries; last: number; y: number } => e != null);
            const ys = spreadLabels(
              ends.map((e) => e.y),
              15,
              margin.top + 8,
              margin.top + innerH,
            );
            return ends.map((e, k) => (
              <text
                key={e.s.key}
                className="end-label fade-in"
                x={x(e.last) + 8}
                y={ys[k]}
                style={{ fill: e.s.color, ["--delay" as string]: "800ms" }}
              >
                {e.s.label}
              </text>
            ));
          })()}

        {hover != null && (
          <g className="noise-free">
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={margin.top}
              y2={margin.top + innerH}
              stroke="var(--c-text)"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            {series.map((s) => {
              const v = s.values[hover];
              return v == null ? null : (
                <circle key={s.key} cx={x(hover)} cy={y(v)} r={4} fill={s.color} stroke="var(--c-surface)" strokeWidth={2} />
              );
            })}
          </g>
        )}
      </svg>

      {hover != null && (
        <div
          className="tooltip"
          style={{
            left: Math.min(Math.max(tooltipLeft + 12, 8), (wrapRef.current?.clientWidth ?? 400) - 190),
            top: 6,
          }}
        >
          <div className="t-head">{xLabels[hover]}</div>
          {series.map((s) => {
            const v = s.values[hover];
            return (
              <div className="t-row" key={s.key}>
                <span>{s.label}</span>
                <span>{v == null ? "–" : `${formatValue(v)} ${unit}`}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
