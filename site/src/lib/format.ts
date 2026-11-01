/* Number and date formatting. The page is English, so en-GB; all market times
   are shown in Europe/Berlin because that is the clock the auction runs on. */

const TZ = "Europe/Berlin";

export function fmtNum(v: number, digits = 0): string {
  // a tick at -0.0 or a value that rounds to zero must not print as "-0"
  if (Math.abs(v) < 0.5 * Math.pow(10, -digits)) v = 0;
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

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const partsFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  weekday: "short",
});

function berlinParts(iso: string): Record<string, string> {
  const p: Record<string, string> = {};
  for (const part of partsFormat.formatToParts(new Date(iso))) p[part.type] = part.value;
  return p;
}

/* Month names come from this table, not from Intl: en-GB spells September "Sept"
   in newer engines and "Sep" in older ones, and the page should not depend on that. */
export function localParts(iso: string): LocalParts {
  const p = berlinParts(iso);
  return {
    date: `${p.year}-${p.month}-${p.day}`,
    hour: Number(p.hour),
    weekday: p.weekday,
    dayLabel: `${p.weekday} ${Number(p.day)} ${MONTHS[Number(p.month) - 1]}`,
  };
}

export function fmtHourLabel(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

/** "28 Oct, 14:50" on the Berlin clock. */
export function fmtDateTime(iso: string): string {
  const p = berlinParts(iso);
  return `${Number(p.day)} ${MONTHS[Number(p.month) - 1]}, ${p.hour}:${p.minute}`;
}

export function fmtDay(iso: string): string {
  return localParts(iso).dayLabel;
}

/** yyyy-mm-dd (a calendar date, no zone) as "27 Oct 2026". */
export function fmtCalendarDate(ymd: string): string {
  const [y, m, d] = ymd.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

/** yyyy-mm-dd or ISO timestamp as "Oct 2026". */
export function fmtMonthYear(iso: string): string {
  const [y, m] = iso.slice(0, 7).split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

/** A price or other quantity that can be negative, with a real minus sign and no plus. */
export function fmtPrice(v: number, digits = 1): string {
  const body = fmtNum(Math.abs(v), digits);
  return v < 0 && Number(body.replace(/,/g, "")) !== 0 ? `\u2212${body}` : body;
}

/** The pipeline writes "EUR/MWh" in generated sentences; the page uses one spelling. */
export function unitSpelling(text: string): string {
  return text.replace(/EUR\/MWh/g, "€/MWh").replace(/EUR\/MW\/yr/g, "€/MW/yr");
}
