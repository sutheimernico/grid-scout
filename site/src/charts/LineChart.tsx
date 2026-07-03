import { useMemo, useRef, useState } from "react";
import { bandPath, extent, linePath, linearScale, ticks } from "./scale";

export interface LineSeries {
  key: string;
  label: string;
  color: string;
  values: (number | null)[];
  dashed?: boolean;
}

interface Band {
  upper: (number | null)[];
  lower: (number | null)[];
  color: string;
  label: string;
}

interface Props {
  series: LineSeries[];
  xLabels: string[]; // one per index, preformatted
  band?: Band;
  height?: number;
  unit: string;
  formatValue?: (v: number) => string;
  xTickEvery?: number;
}

const MARGIN = { top: 12, right: 16, bottom: 26, left: 52 };
const WIDTH = 960;

/** Multi-series line chart: hairline grid, zero baseline, gap-aware lines,
 *  optional quantile band, crosshair + tooltip on hover. */
export function LineChart({
  series,
  xLabels,
  band,
  height = 260,
  unit,
  formatValue = (v) => v.toFixed(0),
  xTickEvery,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);

  const n = xLabels.length;
  const innerW = WIDTH - MARGIN.left - MARGIN.right;
  const innerH = height - MARGIN.top - MARGIN.bottom;

  const { y, yTicks, x } = useMemo(() => {
    const allSeries = series.map((s) => s.values);
    if (band) allSeries.push(band.upper, band.lower);
    let [lo, hi] = extent(allSeries);
    lo = Math.min(lo, 0);
    const pad = (hi - lo) * 0.06;
    const y = linearScale([lo, hi + pad], [MARGIN.top + innerH, MARGIN.top]);
    const x = (i: number) => MARGIN.left + (n <= 1 ? 0 : (i / (n - 1)) * innerW);
    return { y, yTicks: ticks([lo, hi + pad], 5), x };
  }, [series, band, n, innerH, innerW]);

  const step = xTickEvery ?? Math.max(1, Math.round(n / 6));
  const xTickIdx = Array.from({ length: n }, (_, i) => i).filter((i) => i % step === 0);

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * WIDTH;
    const i = Math.round(((px - MARGIN.left) / innerW) * (n - 1));
    setHover(i >= 0 && i < n ? i : null);
  }

  const tooltipLeft =
    hover != null && wrapRef.current
      ? (x(hover) / WIDTH) * wrapRef.current.clientWidth
      : 0;

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
        {yTicks.map((t) => (
          <g key={t}>
            <line
              x1={MARGIN.left}
              x2={WIDTH - MARGIN.right}
              y1={y(t)}
              y2={y(t)}
              stroke={t === 0 ? "var(--baseline)" : "var(--grid-hairline)"}
              strokeWidth={1}
            />
            <text x={MARGIN.left - 8} y={y(t) + 3.5} textAnchor="end">
              {formatValue(t)}
            </text>
          </g>
        ))}
        {xTickIdx.map((i) => (
          <text key={i} x={x(i)} y={height - 8} textAnchor="middle">
            {xLabels[i]}
          </text>
        ))}

        {band && <path d={bandPath(band.upper, band.lower, x, (v) => y(v))} fill={band.color} opacity={0.16} />}

        {series.map((s) => (
          <path
            key={s.key}
            d={linePath(s.values, x, (v) => y(v))}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeDasharray={s.dashed ? "5 5" : undefined}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}

        {hover != null && (
          <g>
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={MARGIN.top}
              y2={MARGIN.top + innerH}
              stroke="var(--ink-muted)"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            {series.map((s) => {
              const v = s.values[hover];
              return v == null ? null : (
                <circle
                  key={s.key}
                  cx={x(hover)}
                  cy={y(v)}
                  r={4}
                  fill={s.color}
                  stroke="var(--surface)"
                  strokeWidth={2}
                />
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
                <span>
                  <span className="swatch" style={{ background: s.color, width: 8, height: 8, display: "inline-block", borderRadius: 2, marginRight: 6 }} />
                  {s.label}
                </span>
                <span className="t-val">{v == null ? "–" : `${formatValue(v)} ${unit}`}</span>
              </div>
            );
          })}
          {band && hover != null && band.upper[hover] != null && band.lower[hover] != null && (
            <div className="t-row">
              <span style={{ color: "var(--ink-muted)" }}>{band.label}</span>
              <span className="t-val" style={{ color: "var(--ink-muted)" }}>
                {formatValue(band.lower[hover]!)}–{formatValue(band.upper[hover]!)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
