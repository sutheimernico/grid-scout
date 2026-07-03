import { useMemo, useRef, useState } from "react";
import { linearScale, ticks } from "./scale";

export interface StackSeries {
  key: string;
  label: string;
  color: string;
  values: (number | null)[];
}

interface Props {
  series: StackSeries[]; // bottom-first stack order
  xLabels: string[];
  height?: number;
  unit: string;
  formatValue?: (v: number) => string;
}

const MARGIN = { top: 12, right: 16, bottom: 26, left: 52 };
const WIDTH = 960;

/** Stacked area (composition over time). Hairline surface-colored separators
 *  between bands stand in for the 2px spacer rule of stacked bars. */
export function StackedArea({ series, xLabels, height = 280, unit, formatValue = (v) => v.toFixed(0) }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const n = xLabels.length;
  const innerW = WIDTH - MARGIN.left - MARGIN.right;
  const innerH = height - MARGIN.top - MARGIN.bottom;

  const { stacked, y, yTicks, x } = useMemo(() => {
    // cumulative sums bottom-up; null counts as 0 in the stack but is
    // remembered so the tooltip can say "no data"
    const cum: number[][] = [];
    let prev = new Array(n).fill(0);
    for (const s of series) {
      const top = prev.map((p, i) => p + (s.values[i] ?? 0));
      cum.push(top);
      prev = top;
    }
    const total = cum[cum.length - 1] ?? new Array(n).fill(0);
    const hi = Math.max(...total, 1);
    const y = linearScale([0, hi * 1.04], [MARGIN.top + innerH, MARGIN.top]);
    const x = (i: number) => MARGIN.left + (n <= 1 ? 0 : (i / (n - 1)) * innerW);
    return { stacked: cum, y, yTicks: ticks([0, hi * 1.04], 4), x };
  }, [series, n, innerH, innerW]);

  function areaPath(upper: number[], lower: number[]): string {
    const up = upper.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    const down = lower.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).reverse();
    return `M${up.join("L")}L${down.join("L")}Z`;
  }

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * WIDTH;
    const i = Math.round(((px - MARGIN.left) / innerW) * (n - 1));
    setHover(i >= 0 && i < n ? i : null);
  }

  const step = Math.max(1, Math.round(n / 6));
  const zeros = new Array(n).fill(0);
  const tooltipLeft =
    hover != null && wrapRef.current ? (x(hover) / WIDTH) * wrapRef.current.clientWidth : 0;

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg
        viewBox={`0 0 ${WIDTH} ${height}`}
        width="100%"
        role="img"
        aria-label={`Stacked area chart of ${series.map((s) => s.label).join(", ")} in ${unit}`}
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
        {series.map((s, si) => (
          <path
            key={s.key}
            d={areaPath(stacked[si], si === 0 ? zeros : stacked[si - 1])}
            fill={s.color}
            stroke="var(--surface)"
            strokeWidth={1.5}
          />
        ))}
        {Array.from({ length: n }, (_, i) => i)
          .filter((i) => i % step === 0)
          .map((i) => (
            <text key={i} x={x(i)} y={height - 8} textAnchor="middle">
              {xLabels[i]}
            </text>
          ))}
        {hover != null && (
          <line
            x1={x(hover)}
            x2={x(hover)}
            y1={MARGIN.top}
            y2={MARGIN.top + innerH}
            stroke="var(--ink)"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        )}
      </svg>

      {hover != null && (
        <div
          className="tooltip"
          style={{
            left: Math.min(Math.max(tooltipLeft + 12, 8), (wrapRef.current?.clientWidth ?? 400) - 210),
            top: 6,
          }}
        >
          <div className="t-head">{xLabels[hover]}</div>
          {[...series].reverse().map((s) => {
            const v = s.values[hover];
            return (
              <div className="t-row" key={s.key}>
                <span>
                  <span
                    style={{
                      background: s.color,
                      width: 8,
                      height: 8,
                      display: "inline-block",
                      borderRadius: 2,
                      marginRight: 6,
                    }}
                  />
                  {s.label}
                </span>
                <span className="t-val">{v == null ? "–" : `${formatValue(v)} ${unit}`}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
