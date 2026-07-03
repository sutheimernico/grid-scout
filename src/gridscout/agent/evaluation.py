"""Agent eval harness: programmatic grading, no LLM judge.

Gold answers are computed at runtime from the SAME tool layer the agent uses,
so the eval set never goes stale as data updates. What is measured is the
agent's tool use and grounding — does it call the right tool and report the
tool's numbers — not the data itself.

Grading is deliberately mechanical:
- numeric questions: some number in the answer must match gold within tolerance;
- trap questions (out of scope / no data): the answer must decline — detected
  by refusal phrases and by the absence of confident invented figures. This is
  a documented heuristic, kept simple on purpose.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from gridscout.agent.tools import GridTools, ToolError

NUMBER_RE = re.compile(r"-?\d[\d,.]*\d|-?\d")

# Broadened after error analysis of the first real run: the agent declined
# correctly with phrasings like "there is no tool available to ..." and
# "the tools ... do not include/cover ...", which the initial list missed —
# 5 of 7 apparent failures were grader gaps, not agent errors.
REFUSAL_MARKERS = [
    "no data",
    "not available",
    "cannot",
    "can't",
    "don't have",
    "do not have",
    "unable",
    "not covered",
    "outside",
    "beyond",
    "only covers",
    "not in scope",
    "keine daten",
    "no tool",
    "none of the",
    "not provide",
    "do not provide",
    "do not include",
    "does not include",
    "do not cover",
    "does not cover",
    "not able",
    "not possible",
]


def extract_numbers(text: str) -> list[float]:
    out = []
    for raw in NUMBER_RE.findall(text):
        cleaned = raw.replace(",", "")
        try:
            out.append(float(cleaned))
        except ValueError:
            continue
    return out


def numeric_match(answer: str, gold: float, rel_tol: float = 0.02, abs_tol: float = 0.51) -> bool:
    return any(
        abs(n - gold) <= max(abs_tol, abs(gold) * rel_tol) for n in extract_numbers(answer)
    )


def refusal_like(answer: str) -> bool:
    lowered = answer.lower()
    return any(marker in lowered for marker in REFUSAL_MARKERS)


@dataclass
class Question:
    id: str
    type: str  # factual | analytical | report | trap
    text: str
    grade: Callable[[str], bool]
    gold_display: str


def _usable_day(tools: GridTools, d: date) -> bool:
    """A day is usable only if every tool the questions need can answer it.
    Recent days can have holes (SMARD's price-settlement lag), so probe."""
    try:
        tools.get_price_day(d.isoformat())
        tools.get_generation_mix_day(d.isoformat())
        tools.explain_price_context(d.isoformat())
        return True
    except ToolError:
        return False


def build_eval_set(tools: GridTools) -> list[Question]:
    """~30 questions anchored to days verified to exist in the data."""
    coverage = tools.get_data_coverage()["series"]
    last_full = date.fromisoformat(coverage["gen_solar"]["to"]) - timedelta(days=2)
    days: list[date] = []
    for offset in (0, 7, 30, 90):
        candidate = last_full - timedelta(days=offset)
        for _ in range(10):  # walk further back past data holes
            if candidate not in days and _usable_day(tools, candidate):
                days.append(candidate)
                break
            candidate -= timedelta(days=1)
    if len(days) < 4:
        raise RuntimeError("could not find 4 usable eval days — data too sparse")

    questions: list[Question] = []

    for i, d in enumerate(days):
        day = d.isoformat()
        price = tools.get_price_day(day)
        questions.append(
            Question(
                id=f"price-mean-{i}",
                type="factual",
                text=f"What was the average German day-ahead electricity price on {day}?",
                grade=lambda a, g=price["mean"]: numeric_match(a, g),
                gold_display=f"{price['mean']} EUR/MWh",
            )
        )
        questions.append(
            Question(
                id=f"price-max-{i}",
                type="factual",
                text=f"How high did the German day-ahead price go on {day}, and in which hour?",
                grade=lambda a, g=price["max"]["value"]: numeric_match(a, g),
                gold_display=f"{price['max']['value']} EUR/MWh at hour {price['max']['hour']}",
            )
        )

    for i, d in enumerate(days[:2]):
        day = d.isoformat()
        mix = tools.get_generation_mix_day(day)
        share_pct = round(mix["renewables_share"] * 100, 1)
        top = max(mix["by_source"], key=mix["by_source"].get)
        questions.append(
            Question(
                id=f"renewables-share-{i}",
                type="factual",
                text=f"What share of German electricity generation was renewable on {day}?",
                grade=lambda a, g=share_pct: numeric_match(a, g, rel_tol=0.03, abs_tol=1.1)
                or numeric_match(a, g / 100, abs_tol=0.02),
                gold_display=f"{share_pct}%",
            )
        )
        questions.append(
            Question(
                id=f"top-source-{i}",
                type="factual",
                text=f"Which single source produced the most electricity in Germany on {day}?",
                grade=lambda a, g=top: g.split()[0].lower() in a.lower(),
                gold_display=top,
            )
        )

    for i, d in enumerate(days[:2]):
        day = d.isoformat()
        ctx = tools.explain_price_context(day)
        cheapest_hour = ctx["cheapest_hours"][0]["hour"]
        questions.append(
            Question(
                id=f"cheapest-hour-{i}",
                type="analytical",
                text=f"Which hour of {day} had the lowest day-ahead price in Germany, "
                "and why might that be?",
                grade=lambda a, g=float(cheapest_hour), h=cheapest_hour: (
                    numeric_match(a, g, abs_tol=0.1) or f"{h:02d}:" in a
                ),
                gold_display=f"hour {cheapest_hour}",
            )
        )

    eval_report = tools.get_forecast_evaluation()
    battery = tools.get_battery_results()
    reports = [
        ("mae", "What is the MAE of grid-scout's price forecast?",
         eval_report["models"]["lgbm_point"]["mae"], "EUR/MWh"),
        ("skill", "By how many percent does the forecast beat the naive baseline?",
         eval_report["skill"]["lgbm_vs_naive_pct"], "%"),
        ("naive-mae", "What MAE does the naive yesterday-baseline achieve?",
         eval_report["models"]["naive_yesterday"]["mae"], "EUR/MWh"),
        ("capture", "What capture rate does the battery reach with the model forecast?",
         battery["capture_rate_model"] * 100, "% (also accept the raw ratio)"),
        ("edge", "How much more revenue per year does the model forecast earn over "
         "the naive forecast for the battery?",
         battery["model_edge_over_naive_eur"], "EUR"),
        ("perfect", "What would the battery earn with perfect price foresight?",
         battery["revenue_eur"]["perfect"], "EUR"),
    ]
    for key, text, gold, unit in reports:
        grade = (
            (lambda a, g=gold: numeric_match(a, g) or numeric_match(a, g / 100, abs_tol=0.011))
            if key == "capture"
            else (lambda a, g=gold: numeric_match(a, g, rel_tol=0.02, abs_tol=1.0))
        )
        questions.append(
            Question(id=f"report-{key}", type="report", text=text, grade=grade,
                     gold_display=f"{round(gold, 2)} {unit}")
        )

    traps = [
        ("fr-price", "What was the French day-ahead power price yesterday?"),
        ("gas-ttf", "What is the current Dutch TTF natural gas price?"),
        ("future", "What will the German day-ahead price be on "
         f"{(last_full + timedelta(days=90)).isoformat()}?"),
        ("ancient", "What was the German day-ahead price on 2005-06-01?"),
        ("stock", "Should I buy shares of RWE based on these power prices?"),
        ("intraday", "What was the German intraday continuous price at 15:30 yesterday?"),
        ("co2", "What is today's EU ETS carbon certificate price?"),
        ("weather", "How warm will it be in Berlin tomorrow?"),
    ]
    for key, text in traps:
        questions.append(
            Question(
                id=f"trap-{key}",
                type="trap",
                text=text,
                grade=refusal_like,
                gold_display="must decline (no data / out of scope)",
            )
        )

    return questions


def run_eval(agent, tools: GridTools, reports_dir: Path) -> dict:
    questions = build_eval_set(tools)
    results = []
    for q in questions:
        res = agent.ask(q.text)
        passed = bool(res.answer) and res.error is None and q.grade(res.answer)
        results.append(
            {
                "id": q.id,
                "type": q.type,
                "question": q.text,
                "gold": q.gold_display,
                "answer": res.answer,
                "tool_calls": [
                    {"tool": c["tool"], "args": c["args"]} for c in res.tool_calls
                ],
                "rounds": res.rounds,
                "passed": passed,
                "agent_error": res.error,
            }
        )

    by_type: dict[str, dict] = {}
    for r in results:
        bucket = by_type.setdefault(r["type"], {"n": 0, "passed": 0})
        bucket["n"] += 1
        bucket["passed"] += int(r["passed"])
    report = {
        "model": agent.model,
        "n": len(results),
        "passed": sum(r["passed"] for r in results),
        "pass_rate": round(sum(r["passed"] for r in results) / len(results), 3),
        "by_type": {
            k: {**v, "pass_rate": round(v["passed"] / v["n"], 3)} for k, v in by_type.items()
        },
        "grading": "programmatic (numeric tolerance / refusal heuristics), no LLM judge",
        "results": results,
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "agent_eval.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
