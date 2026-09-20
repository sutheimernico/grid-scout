/** Contribution-graph calendar: one cell per day, columns are ISO weeks.
 *
 *  Hand-rolled SVG like the rest of the charts. Intensity is runs/expected in
 *  four steps, and a day with no run stays visibly empty — the point of the
 *  panel is that a gap is as readable as a streak.
 */

const CELL = 11;
const GAP = 3;
const TOP = 16;
const LEFT = 26;
const WEEKDAY_LABELS = ["Mon", "", "Wed", "", "Fri", "", ""];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export interface HeatmapDay {
  date: string;
  runs: number;
}

interface Props {
  days: HeatmapDay[];
  expectedPerDay: number;
  color?: string;
  emptyColor?: string;
  label: string;
}

/** Monday-based weekday index, so a week is one column. */
function weekdayIndex(iso: string): number {
  return (new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7;
}

export function intensity(runs: number, expected: number): number {
  if (runs <= 0) return 0;
  const ratio = runs / Math.max(expected, 1);
  if (ratio >= 1) return 1;
  if (ratio >= 0.6) return 0.72;
  if (ratio >= 0.3) return 0.48;
  return 0.26;
}

/** Column (week) index per day, counting from the first day's week. */
export function layout(days: HeatmapDay[]): { day: HeatmapDay; col: number; row: number }[] {
  if (!days.length) return [];
  const firstRow = weekdayIndex(days[0].date);
  return days.map((day, i) => {
    const offset = i + firstRow;
    return { day, col: Math.floor(offset / 7), row: offset % 7 };
  });
}

export function Heatmap({ days, expectedPerDay, color = "var(--good)", emptyColor = "var(--grid-hairline)", label }: Props) {
  const cells = layout(days);
  const columns = cells.length ? cells[cells.length - 1].col + 1 : 0;
  const width = LEFT + columns * (CELL + GAP);
  const height = TOP + 7 * (CELL + GAP);

  const monthTicks: { col: number; name: string }[] = [];
  let lastMonth = -1;
  for (const { day, col } of cells) {
    const month = Number(day.date.slice(5, 7)) - 1;
    if (month !== lastMonth) {
      monthTicks.push({ col, name: MONTHS[month] });
      lastMonth = month;
    }
  }

  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={label}>
        {monthTicks.map((t) => (
          <text key={`${t.name}-${t.col}`} x={LEFT + t.col * (CELL + GAP)} y={10} textAnchor="start">
            {t.name}
          </text>
        ))}
        {WEEKDAY_LABELS.map((name, row) =>
          name ? (
            <text key={name} x={LEFT - 6} y={TOP + row * (CELL + GAP) + CELL - 1} textAnchor="end">
              {name}
            </text>
          ) : null,
        )}
        {cells.map(({ day, col, row }) => {
          const alpha = intensity(day.runs, expectedPerDay);
          return (
            <rect
              key={day.date}
              x={LEFT + col * (CELL + GAP)}
              y={TOP + row * (CELL + GAP)}
              width={CELL}
              height={CELL}
              rx={2}
              fill={alpha === 0 ? emptyColor : color}
              opacity={alpha === 0 ? 1 : alpha}
            >
              <title>{`${day.date}: ${day.runs} run${day.runs === 1 ? "" : "s"}`}</title>
            </rect>
          );
        })}
      </svg>
    </div>
  );
}
