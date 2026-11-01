/* Number and date formatting. The page is English, so en-GB; all market times
   are shown in Europe/Berlin because that is the clock the auction runs on. */

const TZ = "Europe/Berlin";

export function fmtNum(v: number, digits = 0): string {
  return v.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Explicit sign, true minus sign for negatives. */
export function fmtSigned(v: number, digits = 0): string {
  const body = fmtNum(Math.abs(v), digits);
  if (v > 0) return `+${body}`;
  if (v < 0) return `−${body}`;
  return body;
}

export function fmtPct(fraction: number, digits = 1): string {
  return `${fmtNum(fraction * 100, digits)}%`;
}

export interface LocalParts {
  /** yyyy-mm-dd on the Berlin clock */
  date: string;
  hour: number;
  weekday: string;
  /** e.g. "Tue 27 Oct" */
  dayLabel: string;
}

const partsFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  hourCycle: "h23",
  weekday: "short",
});
const monthShort = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, month: "short" });

export function localParts(iso: string): LocalParts {
  const d = new Date(iso);
  const p: Record<string, string> = {};
  for (const part of partsFormat.formatToParts(d)) p[part.type] = part.value;
  return {
    date: `${p.year}-${p.month}-${p.day}`,
    hour: Number(p.hour),
    weekday: p.weekday,
    dayLabel: `${p.weekday} ${Number(p.day)} ${monthShort.format(d)}`,
  };
}

export function fmtHourLabel(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

export function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    timeZone: TZ,
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtDay(iso: string): string {
  return localParts(iso).dayLabel;
}

/** yyyy-mm-dd (a calendar date, no zone) as "27 Oct 2026". */
export function fmtCalendarDate(ymd: string): string {
  return new Date(`${ymd}T12:00:00Z`).toLocaleDateString("en-GB", {
    timeZone: "UTC",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
