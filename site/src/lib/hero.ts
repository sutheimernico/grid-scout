import { localParts } from "./format";

export interface RecentSeries {
  timestamps: string[];
  actual: (number | null)[];
  predicted: (number | null)[];
  q10: (number | null)[];
  q90: (number | null)[];
}

export interface DaySpan {
  date: string;
  label: string;
  /** index range [from, to) inside the window */
  from: number;
  to: number;
}

export interface HeroWindow extends RecentSeries {
  days: DaySpan[];
  /** index ranges [from, to) of consecutive hours that cleared below zero */
  negativeSpans: [number, number][];
  stats: {
    nHours: number;
    mae: number | null;
    /** share of hours where the actual price sat inside the raw p10-p90 band */
    coverage: number | null;
  };
}

/** Consecutive runs of values below zero as [from, to) index ranges. */
export function negativeSpans(values: (number | null)[]): [number, number][] {
  const spans: [number, number][] = [];
  let start = -1;
  values.forEach((v, i) => {
    const neg = v != null && v < 0;
    if (neg && start < 0) start = i;
    if (!neg && start >= 0) {
      spans.push([start, i]);
      start = -1;
    }
  });
  if (start >= 0) spans.push([start, values.length]);
  return spans;
}

/** The last `maxDays` complete delivery days (Europe/Berlin calendar days, so a
 *  23- or 25-hour DST day counts as one) of the backtest series. A day is
 *  complete when it has at least 23 hourly points. Returns null when no day
 *  qualifies, so the caller can show an honest empty state. */
export function pickHeroWindow(recent: RecentSeries, maxDays = 3): HeroWindow | null {
  const byDay = new Map<string, number[]>();
  recent.timestamps.forEach((ts, i) => {
    const date = localParts(ts).date;
    const list = byDay.get(date) ?? [];
    list.push(i);
    byDay.set(date, list);
  });
  const complete = [...byDay.entries()].filter(([, idx]) => idx.length >= 23).slice(-maxDays);
  if (!complete.length) return null;

  const indices = complete.flatMap(([, idx]) => idx);
  const pick = <T,>(arr: T[]) => indices.map((i) => arr[i]);
  const timestamps = pick(recent.timestamps);
  const actual = pick(recent.actual);
  const predicted = pick(recent.predicted);
  const q10 = pick(recent.q10);
  const q90 = pick(recent.q90);

  let cursor = 0;
  const days: DaySpan[] = complete.map(([date, idx]) => {
    const span = { date, label: localParts(recent.timestamps[idx[0]]).dayLabel, from: cursor, to: cursor + idx.length };
    cursor += idx.length;
    return span;
  });

  let errSum = 0;
  let errN = 0;
  let inside = 0;
  let bandN = 0;
  actual.forEach((a, i) => {
    if (a == null) return;
    const p = predicted[i];
    if (p != null) {
      errSum += Math.abs(a - p);
      errN += 1;
    }
    const lo = q10[i];
    const hi = q90[i];
    if (lo != null && hi != null) {
      bandN += 1;
      if (a >= lo && a <= hi) inside += 1;
    }
  });

  return {
    timestamps,
    actual,
    predicted,
    q10,
    q90,
    days,
    negativeSpans: negativeSpans(actual),
    stats: {
      nHours: timestamps.length,
      mae: errN ? errSum / errN : null,
      coverage: bandN ? inside / bandN : null,
    },
  };
}
