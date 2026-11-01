import { LineChart } from "../charts/LineChart";
import { fmtCalendarDate, fmtDateTime, fmtNum, fmtSigned } from "../lib/format";
import { ledgerRows, ledgerScaleMax } from "../lib/ledger";
import type { Loadable } from "../lib/useData";
import type { ForwardLedgerData } from "../types";
import { Reveal } from "../ui";

const VISIBLE_DAYS = 14;

/* The protocol is a description of what the pipeline does, not a measurement,
   and the page says so. It is the reason a scored row can be trusted. */
function Protocol() {
  return (
    <Reveal>
      <span className="protocol-label">The protocol, not data: what happens to every forecast</span>
      <ol className="protocol">
        <li>
          <time>before 12:00</time>
          <b>Forecast recorded</b>
          24 hourly prices for tomorrow are appended to the ledger. The command refuses to run once the clock has
          passed 12:00.
        </li>
        <li className="gate">
          <time>12:00</time>
          <b>Auction closes</b>
          Day-ahead gate closure. From here the forecast can no longer be adjusted, and nothing dated on the delivery
          day was used.
        </li>
        <li>
          <time>delivery day</time>
          <b>Prices clear</b>
          The 24 hours are delivered at the auction price. SMARD publishes them with a delay.
        </li>
        <li className="scored">
          <time>when published</time>
          <b>Scored</b>
          The record is scored against both naive baselines. Scored records are never overwritten.
        </li>
      </ol>
    </Reveal>
  );
}

/* The forward test: predictions written down before the auction, scored later.
   Three honest states: no ledger yet, entries still pending, entries scored. */
export function Ledger({ ledger }: { ledger: Loadable<ForwardLedgerData> }) {
  const data = ledger.state === "ready" ? ledger.data : null;
  const cum = data?.summary.cumulative ?? null;
  const week = data?.summary.last_7_days ?? null;

  return (
    <section className="band inverse" id="ledger" aria-label="Live forward test">
      <div className="wrap">
        <div className="ledger-head">
          <Reveal>
            <h2>The ledger: forecasts written down before the auction</h2>
          </Reveal>
          <Reveal>
            <p className="lede" style={{ color: "var(--ink-2)" }}>
              {data
                ? data.method
                : "A backtest can be re-run until it looks good. This cannot: every morning the pipeline records tomorrow's forecast, and the cleared prices score it afterwards."}
            </p>
          </Reveal>
        </div>

        {!data && (
          <div className="empty-ledger">
            <p className="statement">
              {ledger.state === "loading"
                ? "loading the forward ledger…"
                : "No forward ledger yet — the daily pre-auction run starts it. Everything above is the backtest."}
            </p>
            <Protocol />
          </div>
        )}

        {data && (
          <>
            <Reveal className="ledger-sums">
              <div>
                <b>{data.summary.n_records}</b>
                <span>
                  Forecasts recorded
                  <br />
                  {data.summary.first_target_date
                    ? `since ${fmtCalendarDate(data.summary.first_target_date)} · ${data.summary.n_pending} awaiting their prices`
                    : "none yet"}
                </span>
              </div>
              <div>
                <b>{data.summary.n_scored}</b>
                <span>
                  Scored days
                  <br />
                  {cum ? `${cum.n_hours} delivered hours` : "first scores arrive a day after the first forecast"}
                </span>
              </div>
              {cum && (
                <>
                  <div>
                    <b>{fmtNum(cum.mae_model, 2)}</b>
                    <span>
                      MAE model (cumulative)
                      <br />
                      €/MWh
                    </span>
                  </div>
                  <div>
                    <b>{fmtNum(cum.mae_naive, 2)}</b>
                    <span>
                      MAE naive (cumulative)
                      <br />
                      model beat naive on {cum.days_model_beat_naive}/{cum.n_days} days
                    </span>
                  </div>
                </>
              )}
            </Reveal>
            {week && (
              <p className="small" style={{ marginTop: -16, marginBottom: 32 }}>
                Last 7 days: model {fmtNum(week.mae_model, 1)} / naive {fmtNum(week.mae_naive, 1)} €/MWh
              </p>
            )}
            {cum == null && (
              <p className="statement" style={{ fontFamily: "var(--display)", fontSize: 24, fontWeight: 700, maxWidth: "36ch", margin: "0 0 36px" }}>
                No scored day yet. Nothing here is claimed until the cleared prices arrive — that is the whole point of
                a forward test.
              </p>
            )}

            <DayList days={data.days} />
            {cum == null && <div style={{ marginTop: 56 }}><Protocol /></div>}
            <LatestForecast latest={data.latest} />
          </>
        )}
      </div>
    </section>
  );
}

function DayList({ days }: { days: ForwardLedgerData["days"] }) {
  const all = ledgerRows(days);
  const rows = all.slice(0, VISIBLE_DAYS);
  const max = ledgerScaleMax(rows);
  const pct = (v: number) => `${(v / max) * 100}%`;
  if (!rows.length) return null;
  return (
    <Reveal>
      <p className="ledger-key">
        <span>
          <i style={{ background: "var(--volt)" }} />
          Forecast MAE
        </span>
        <span>
          <i style={{ border: "2px solid var(--naive)" }} />
          Naive MAE
        </span>
        <span>€/MWh per delivery day, scale 0 to {max}. A green link means the forecast was closer.</span>
      </p>
      <ul className="ledger-list">
        {rows.map((r) => (
          <li className={`ledger-row ${r.outcome}`} key={r.date}>
            <span className="d">{fmtCalendarDate(r.date).replace(/ \d{4}$/, "")}</span>
            <span className="dumbbell">
              {r.maeModel != null && r.maeNaive != null && (
                <>
                  <i
                    className="link"
                    style={{
                      left: pct(Math.min(r.maeModel, r.maeNaive)),
                      width: pct(Math.abs(r.maeNaive - r.maeModel)),
                      background: r.outcome === "win" ? "var(--volt)" : "var(--neg)",
                    }}
                  />
                  <i className="pt n" style={{ left: pct(r.maeNaive) }} />
                  <i className="pt m" style={{ left: pct(r.maeModel) }} />
                </>
              )}
            </span>
            <span className="nums">
              {r.maeModel != null && r.maeNaive != null ? (
                <>
                  <b>{fmtNum(r.maeModel, 1)}</b> vs {fmtNum(r.maeNaive, 1)}{" "}
                  <span>({fmtSigned(r.gain ?? 0, 1)})</span>
                </>
              ) : (
                "pending"
              )}
            </span>
          </li>
        ))}
      </ul>
      {all.length > rows.length && (
        <p className="small" style={{ marginTop: 10 }}>
          {all.length - rows.length} older delivery {all.length - rows.length === 1 ? "day is" : "days are"} in the ledger file.
        </p>
      )}
    </Reveal>
  );
}

function LatestForecast({ latest }: { latest: ForwardLedgerData["latest"] }) {
  if (!latest) return null;
  return (
    <Reveal className="latest">
      <p className="subhead" style={{ color: "#f1f3f2" }}>
        Delivery day {fmtCalendarDate(latest.target_date)}, predicted {fmtDateTime(latest.generated_at_utc)}
        {latest.scored ? " · cleared prices overlaid" : " · outcome still open"}
      </p>
      <LineChart
        series={[
          ...(latest.actual
            ? [{ key: "actual", label: "Cleared", color: "var(--c-actual)", values: latest.actual as (number | null)[] }]
            : []),
          { key: "pred", label: "Forecast", color: "var(--c-model)", values: latest.pred_model as (number | null)[], width: 2.75 },
          { key: "naive", label: "Naive", color: "var(--c-naive)", values: latest.pred_naive as (number | null)[], dashed: true },
        ]}
        endLabels
        xLabels={latest.hours_local.map((h) => `${String(h).padStart(2, "0")}:00`)}
        unit="€/MWh"
        xTickEvery={3}
      />
    </Reveal>
  );
}
