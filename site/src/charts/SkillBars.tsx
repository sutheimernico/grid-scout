/** Skill-vs-baseline bars: one bar per segment, zero line in the middle.
 *
 *  Up and green means the model beat the naive baseline in that slice, down and
 *  red means it lost. Losing segments are the reason this chart exists, so they
 *  are drawn in the same view rather than filtered out.
 */

import { linearScale, ticks } from "./scale";
import { useChartWidth } from "../lib/useChartWidth";
import { useRef } from "react";

export interface Segment {
  segment: string;
  n: number;
  mae_model: number;
  mae_naive: number;
  skill_vs_naive_pct: number | null;
  best: string;
}

interface Props {
  segments: Segment[];
  label: string;
  height?: number;
  labelEvery?: number;
}

const MARGIN = { top: 10, right: 12, bottom: 24, left: 42 };

export function SkillBars({ segments, label, height = 170, labelEvery = 1 }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const WIDTH = useChartWidth(wrapRef);
  const innerW = WIDTH - MARGIN.left - MARGIN.right;
  const innerH = height - MARGIN.top - MARGIN.bottom;
  const values = segments.map((s) => s.skill_vs_naive_pct ?? 0);
  const hi = Math.max(5, ...values);
  const lo = Math.min(-5, ...values);
  const y = linearScale([lo, hi], [MARGIN.top + innerH, MARGIN.top]);
  const slot = innerW / Math.max(segments.length, 1);
  const barW = Math.max(4, slot * 0.62);

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg viewBox={`0 0 ${WIDTH} ${height}`} width="100%" role="img" aria-label={label}>
        {ticks([lo, hi], 4).map((t) => (
          <g key={t}>
            <line
              x1={MARGIN.left}
              x2={WIDTH - MARGIN.right}
              y1={y(t)}
              y2={y(t)}
              stroke={t === 0 ? "var(--baseline)" : "var(--grid-hairline)"}
            />
            <text x={MARGIN.left - 8} y={y(t) + 3.5} textAnchor="end">
              {t}%
            </text>
          </g>
        ))}
        {segments.map((s, i) => {
          const value = s.skill_vs_naive_pct ?? 0;
          const x = MARGIN.left + i * slot + (slot - barW) / 2;
          const top = value >= 0 ? y(value) : y(0);
          return (
            <g key={s.segment}>
              <rect
                x={x}
                y={top}
                width={barW}
                height={Math.max(1, Math.abs(y(value) - y(0)))}
                fill={value >= 0 ? "var(--good)" : "var(--critical)"}
                opacity={0.85}
              >
                <title>
                  {`${s.segment}: model ${s.mae_model.toFixed(2)} vs naive ${s.mae_naive.toFixed(2)} EUR/MWh over ${s.n} hours`}
                </title>
              </rect>
              {i % Math.max(labelEvery, Math.ceil(36 / slot)) === 0 && (
                <text x={x + barW / 2} y={height - 8} textAnchor="middle">
                  {s.segment}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
