import { fmtNum, prettyText } from "../lib/format";
import type { AgentData } from "../types";
import { CountUp, Reveal } from "../ui";
import { useInView } from "../lib/motion";

const TYPE_LABEL: Record<string, string> = {
  factual: "Factual",
  analytical: "Analytical",
  report: "Report",
  trap: "Trap",
};
export const typeLabel = (t: string) => TYPE_LABEL[t] ?? t.charAt(0).toUpperCase() + t.slice(1);

function QuestionRow({ type, n, passed, why, seen }: { type: string; n: number; passed: number; why: string; seen: boolean }) {
  return (
    <div className="q-row" role="row">
      <span role="rowheader">
        {typeLabel(type)} questions
        <span className="why">{why}</span>
      </span>
      <span className="q-grid" aria-hidden="true">
        {Array.from({ length: n }, (_, i) => (
          <i
            key={i}
            className={`q fade-in ${i < passed ? "" : "fail"}`}
            style={{ ["--delay" as string]: `${i * 18}ms` }}
            title={i < passed ? "passed" : "failed"}
          />
        ))}
      </span>
      <span className="score" role="cell">
        {passed}/{n}
      </span>
      {seen && null}
    </div>
  );
}

export function Agent({ data }: { data: AgentData }) {
  const [ref, seen] = useInView<HTMLDivElement>(0.25);
  return (
    <section className="band tint" id="agent" aria-label="Local LLM agent evaluation">
      <div className="wrap">
        <div className="split">
          <div className={`stack reveal ${seen ? "is-in" : ""}`} ref={ref}>
            <h2>A local LLM you can check the math on</h2>
            <p className="note">
              A tool-calling agent (Ollama, runs on your machine — clone the repo, no cloud) answers market questions
              grounded in the same data. It is <em>measured</em>, not demoed: every answer is graded programmatically
              against tool output — numeric tolerance for facts, refusal detection for trap questions it must decline.
              No LLM judge.
              {data.regraded
                ? ` The grader also fails an answer that contradicts itself; ${data.regraded} answer in the stored run had the right number and nonsense around it, so it was regraded offline.`
                : ""}
            </p>
            <div className="big-figure" style={{ marginTop: 28 }}>
              <CountUp value={data.pass_rate * 100} active={seen} format={(v) => `${fmtNum(v, 0)}`} />
              <small>%</small>
            </div>
            <p className="note" style={{ marginTop: 6 }}>
              <b>Overall pass rate</b> on {data.n} development questions · {data.model}, local — grader tuned on these
            </p>
            {data.holdout && (
              <p className="note">
                Untuned holdout: <b>{fmtNum(data.holdout.pass_rate * 100, 0)}%</b> ({data.holdout.passed}/
                {data.holdout.n} questions written after tuning).
              </p>
            )}
            <div role="table" aria-label="Pass rate per question type" style={{ marginTop: 24 }}>
              {Object.entries(data.by_type).map(([type, s]) => (
                <QuestionRow
                  key={type}
                  type={type}
                  n={s.n}
                  passed={s.passed}
                  why={type === "trap" ? "must decline, not invent" : "graded vs tool output"}
                  seen={seen}
                />
              ))}
            </div>
          </div>
          <Reveal className="transcripts">
            <h3 style={{ marginBottom: 6 }}>Sample transcripts, including failures</h3>
            <p className="small" style={{ marginBottom: 14 }}>
              curated one pass + one fail per question type
              {data.generated_utc
                ? ` · recorded ${data.generated_utc.slice(0, 10)}; figures quote that day's data, not today's`
                : ""}
            </p>
            {data.examples.map((ex, i) => (
              <details key={i} open={!ex.passed}>
                <summary>
                  <span className={`badge ${ex.passed ? "badge-pass" : "badge-fail"}`}>{ex.passed ? "PASS" : "FAIL"}</span>
                  <span>
                    <span className="t-type">{typeLabel(ex.type)}</span> {prettyText(ex.question)}
                  </span>
                </summary>
                <div className="t-a">{ex.answer ? prettyText(ex.answer) : <em>(no final answer)</em>}</div>
                <div className="t-meta">
                  gold: {prettyText(ex.gold)}
                  {ex.tools_used.length > 0 && <> · tools: {ex.tools_used.join(", ")}</>}
                </div>
              </details>
            ))}
          </Reveal>
        </div>
      </div>
    </section>
  );
}
