import type { HealthEntry, ReportEntry } from "../types";

/** Hours after which a series that reports "ok" is shown amber / red. SMARD
 *  publishes generation with a lag of about a day, so up to 36 h is normal;
 *  63.8 h on a series that updates every few hours is not "ok". */
export const WARN_AFTER_HOURS = 36;
export const CRITICAL_AFTER_HOURS = 96;

export type Tone = "good" | "warning" | "critical" | "muted";

/** Dot tone for a health row. The pipeline's own verdict wins when it is worse
 *  than the age rule; a retired series is muted, never a fault. */
export function healthTone(s: HealthEntry, sinceExportHours = 0): Tone {
  if (s.status === "discontinued") return "muted";
  if (s.status === "missing") return "critical";
  if (s.status === "stale") return "warning";
  const age = s.age_hours == null ? undefined : s.age_hours + sinceExportHours;
  if (age != null && age >= CRITICAL_AFTER_HOURS) return "critical";
  if (age != null && age >= WARN_AFTER_HOURS) return "warning";
  return "good";
}

/** Hours between the export's own timestamp and now. The artifact records ages
 *  as of its export; a page opened days later must add the time since, or a dead
 *  pipeline would keep showing green dots. Never negative (clock skew). */
export function hoursSince(exportedAtIso: string, now: number = Date.now()): number {
  const t = Date.parse(exportedAtIso);
  return Number.isNaN(t) ? 0 : Math.max(0, (now - t) / 3_600_000);
}

/** Report age in days as of now, and its status graded against the promised cadence. */
export function liveReport(r: ReportEntry, sinceExportHours = 0): { ageDays: number | null; status: ReportEntry["status"] } {
  if (r.age_days == null) return { ageDays: null, status: r.status };
  const ageDays = r.age_days + sinceExportHours / 24;
  if (r.status !== "ok" && r.status !== "aging" && r.status !== "overdue") return { ageDays, status: r.status };
  if (r.overdue_after_days != null && ageDays >= r.overdue_after_days) return { ageDays, status: "overdue" };
  if (r.warn_after_days != null && ageDays >= r.warn_after_days) return { ageDays, status: "aging" };
  return { ageDays, status: r.status === "ok" ? "ok" : r.status };
}
