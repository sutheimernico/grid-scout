/** Skill-vs-baseline bars: one bar per segment, zero line in the middle.
 *
 *  Up and green means the model beat the naive baseline in that slice, down and
 *  red means it lost. Losing segments are the reason this chart exists, so they
 *  are drawn in the same view rather than filtered out.
 */

import { useRef } from "react";
import { linearScale, ticks } from "./scale";
import { useChartWidth } from "../lib/useChartWidth";
import { fmtNum } from "../lib/format";

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
  /** print the value above each bar (for short series) */
  showValues?: boolean;
}

const MARGIN = { top: 20, right: 6, bottom: 26, left: 40 };

export function SkillBars({ segments, label, height = 190, labelEvery = 1, showValues = false }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const WIDTH = useChartWidth(wrapRef);
  const innerW = WIDTH - MARGIN.left - MARGIN.right;
  const innerH = height - MARGIN.top - MARGIN.bottom;
  const values = segments.map((s) => s.skill_vs_naive_pct ?? 0);
  const hi = Math.max(10, ...values) * 1.08;
  const lo = Math.min(0, ...values) * 1.08;
  const y = linearScale([lo, hi], [MARGIN.top + innerH, MARGIN.top]);
  const slot = innerW / Math.max(segments.length, 1);
  const barW = Math.max(4, slot * 0.66);

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
              stroke={t === 0 ? "var(--ink)" : "var(--c-grid)"}
              strokeWidth={t === 0 ? 1.25 : 1}
            />
            <text x={MARGIN.left - 8} y={y(t) + 4} textAnchor="end">
              {t}%
            </text>
          </g>
        ))}
        {segments.map((s, i) => {
          const value = s.skill_vs_naive_pct ?? 0;
          const x = MARGIN.left + i * slot + (slot - barW) / 2;
          const top = value >= 0 ? y(value) : y(0);
          const up = value >= 0;
          return (
            <g key={s.segment}>
              <rect
                className={`grow-y ${up ? "up" : "down"}`}
                style={{ ["--delay" as string]: `${i * 22}ms` }}
                x={x}
                y={top}
                width={barW}
                height={Math.max(1, Math.abs(y(value) - y(0)))}
                fill={up ? "var(--volt)" : "var(--neg)"}
              >
                <title>
                  {`${s.segment}: model ${s.mae_model.toFixed(2)} vs naive ${s.mae_naive.toFixed(2)} EUR/MWh over ${s.n} hours`}
                </title>
              </rect>
              {showValues && (
                <text x={x + barW / 2} y={(up ? top : top + Math.abs(y(value) - y(0))) + (up ? -6 : 14)} textAnchor="middle">
                  {fmtNum(value, 0)}%
                </text>
              )}
              {i % Math.max(labelEvery, Math.ceil(34 / slot)) === 0 && (
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
