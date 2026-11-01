import type { HealthEntry } from "../types";

/** Hours after which a series that reports "ok" is shown amber / red. SMARD
 *  publishes generation with a lag of about a day, so up to 36 h is normal;
 *  63.8 h on a series that updates every few hours is not "ok". */
export const WARN_AFTER_HOURS = 36;
export const CRITICAL_AFTER_HOURS = 96;

export type Tone = "good" | "warning" | "critical" | "muted";

/** Dot tone for a health row. The pipeline's own verdict wins when it is worse
 *  than the age rule; a retired series is muted, never a fault. */
export function healthTone(s: HealthEntry): Tone {
  if (s.status === "discontinued") return "muted";
  if (s.status === "missing") return "critical";
  if (s.status === "stale") return "warning";
  const age = s.age_hours;
  if (age != null && age >= CRITICAL_AFTER_HOURS) return "critical";
  if (age != null && age >= WARN_AFTER_HOURS) return "warning";
  return "good";
}
