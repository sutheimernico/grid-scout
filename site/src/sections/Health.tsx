import { Heatmap } from "../charts/Heatmap";
import { healthTone, type Tone } from "../lib/freshness";
import type { Loadable } from "../lib/useData";
import type { HealthData, HealthEntry, ReportEntry, UptimeData } from "../types";
import { Pending, Reveal } from "../ui";

const TONE_VAR: Record<Tone, string> = {
  good: "var(--good)",
  warning: "var(--warning)",
  critical: "var(--critical)",
  muted: "var(--ink-muted)",
};

/* Report rows: only a report that promised a cadence and missed it turns red.
   A manual, unknown or never-produced report is muted, not an alarm. */
function reportColor(status: ReportEntry["status"]): string {
  if (status === "ok") return "var(--good)";
  if (status === "aging") return "var(--warning)";
  if (status === "overdue") return "var(--critical)";
  return "var(--ink-muted)";
}

function reportAge(r: ReportEntry): string {
  if (r.age_days == null) return r.status;
  return `${r.age_days.toFixed(0)}d`;
}

function healthAge(s: HealthEntry): string {
  if (s.status === "missing") return "missing";
  if (s.status === "discontinued") return "retired";
  // Forecast series run into the future, so their "age" is negative: show how far
  // ahead they reach instead of a nonsensical "-21.2h".
  if (s.age_hours != null && s.age_hours < 0) return `reaches +${Math.round(-s.age_hours)} h`;
  return `${s.age_hours}h`;
}

export function Health({ health, uptime }: { health: Loadable<HealthData>; uptime: Loadable<UptimeData> }) {
  return (
    <section className="band" id="pipeline" aria-label="Pipeline health">
      <div className="wrap">
        <Reveal className="stack" >
          <h2 style={{ maxWidth: "18ch" }}>Nobody operates this</h2>
          <p className="lede">
            GitHub Actions is the scheduler, the repo is the database, and the calendar below is the pipeline&apos;s own
            commit history: one cell per day since it went live. The pipeline opens a GitHub issue on itself when
            something here goes stale.
          </p>
        </Reveal>
        <Uptime uptime={uptime} />
        <Reveal>
          <p className="subhead" style={{ marginTop: 56 }}>Every series this site renders, with its freshness</p>
          {health.state === "ready" ? (
            <>
              <div className="health-list">
                {Object.entries(health.data.series).map(([name, s]) => (
                  <div className="health-item" key={name} title={s.note ?? name}>
                    <span className="dot" style={{ background: TONE_VAR[healthTone(s)] }} />
                    <span className="name">{s.label ?? name}</span>
                    <span className="age">{healthAge(s)}</span>
                  </div>
                ))}
              </div>
              {health.data.reports && Object.keys(health.data.reports).length > 0 && (
                <>
                  <p className="subhead" style={{ marginTop: 40 }}>
                    Derived reports — the numbers above come from these. Fresh raw data says nothing about whether the
                    weekly evaluation still runs.
                  </p>
                  <div className="health-list">
                    {Object.entries(health.data.reports).map(([file, r]) => (
                      <div className="health-item" key={file}>
                        <span className="dot" style={{ background: reportColor(r.status) }} />
                        <span className="name">{r.label}</span>
                        <span className="age">{reportAge(r)}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          ) : (
            <Pending what="health report" state={health.state} />
          )}
        </Reveal>
      </div>
    </section>
  );
}

function Uptime({ uptime }: { uptime: Loadable<UptimeData> }) {
  if (uptime.state !== "ready") {
    return <Pending what="uptime calendar" state={uptime.state} />;
  }
  const { days, totals, reference_runs_per_day, scheduled_runs_per_day, first_day } = uptime.data;
  return (
    <Reveal className="split even" threshold={0.25}>
      <div className="stack" style={{ marginTop: 48 }}>
      <h3 className="facts">
        <span>{totals.days} days live</span>
        <span>{totals.runs} published refreshes</span>
        <span>
          {totals.days_with_zero_runs === 0
            ? "no day without a refresh"
            : `${totals.days_with_zero_runs} ${totals.days_with_zero_runs === 1 ? "day" : "days"} without a refresh${
                totals.days_with_zero_runs > 1 ? `, longest run of ${totals.longest_silent_streak_days} in a row` : ""
              }`}
        </span>
      </h3>
      <p className="note">
        Since {first_day}. A cell counts refreshes the pipeline actually published that day. A run that finds no new
        SMARD data commits nothing, and GitHub delays or skips some scheduled runs, so a pale cell is not an outage — an
        empty one would be. {scheduled_runs_per_day} cron slots per day, median {reference_runs_per_day} published.
      </p>
      </div>
      <div style={{ marginTop: 48 }}>
        <Heatmap days={days} expectedPerDay={reference_runs_per_day} label={`Pipeline runs per day since ${first_day}`} />
      </div>
    </Reveal>
  );
}
