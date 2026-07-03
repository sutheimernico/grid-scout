"""Local agent: Ollama chat with tool calling over GridTools.

Deliberately minimal — no framework. The value is measurable grounding:
every numeric claim must come from a tool result, and the eval harness
checks exactly that.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from gridscout.agent.tools import GridTools, ToolError

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:7b"
MAX_TOOL_ROUNDS = 6

SYSTEM_PROMPT = """\
You are grid-scout, an analyst for the German day-ahead electricity market.
Today is {today} (Europe/Berlin).

Rules, in order of priority:
1. Every number you state MUST come from a tool result in this conversation. \
Never estimate, never fill gaps from memory.
2. If the tools cannot answer (no data, out of scope, wrong market), say so \
plainly and do not invent a substitute answer.
3. Answer compactly: the number(s) first with units, then one sentence of \
context if helpful. No filler.
"""


def _ollama_tool_schema() -> list[dict]:
    def prop(desc: str) -> dict:
        return {"type": "string", "description": desc}

    specs = [
        ("get_price_day", "Hourly German day-ahead prices for one day (EUR/MWh): hourly values, mean, min/max with hour, negative-price hours.", {"day": prop("ISO date YYYY-MM-DD")}),
        ("get_price_range_summary", "Price stats (mean/min/max/negative hours) over an inclusive day range, max 400 days.", {"start_day": prop("ISO date"), "end_day": prop("ISO date")}),
        ("get_generation_mix_day", "Generation per source for one day (MWh) and renewables share.", {"day": prop("ISO date YYYY-MM-DD")}),
        ("explain_price_context", "Why prices were high/low on a day: residual-load correlation, cheapest and priciest hours.", {"day": prop("ISO date YYYY-MM-DD")}),
        ("get_forecast_evaluation", "Out-of-sample evaluation of the price forecast vs baselines (MAE, RMSE, skill).", {}),
        ("get_battery_results", "Battery arbitrage backtest: revenue model/naive/perfect, capture rates.", {}),
        ("get_data_coverage", "Which data series exist and their date coverage.", {}),
    ]
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": params,
                    "required": list(params),
                },
            },
        }
        for name, desc, params in specs
    ]


@dataclass
class AgentResult:
    question: str
    answer: str
    tool_calls: list[dict] = field(default_factory=list)
    rounds: int = 0
    error: str | None = None


class GridAgent:
    def __init__(
        self,
        tools: GridTools | None = None,
        model: str = DEFAULT_MODEL,
        ollama_url: str = OLLAMA_URL,
        timeout: float = 180.0,
    ):
        self.tools = tools or GridTools(Path("data"), Path("reports"))
        self.model = model
        self._http = httpx.Client(base_url=ollama_url, timeout=timeout)
        self._schema = _ollama_tool_schema()

    def ask(self, question: str) -> AgentResult:
        today = datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(today=today)},
            {"role": "user", "content": question},
        ]
        result = AgentResult(question=question, answer="")
        for round_no in range(1, MAX_TOOL_ROUNDS + 1):
            result.rounds = round_no
            response = self._chat(messages)
            message = response["message"]
            calls = message.get("tool_calls") or []
            if not calls:
                result.answer = (message.get("content") or "").strip()
                return result
            messages.append(message)
            for call in calls:
                name = call["function"]["name"]
                args = call["function"].get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                payload = self._dispatch(name, args)
                result.tool_calls.append({"tool": name, "args": args, "result": payload})
                messages.append({"role": "tool", "content": json.dumps(payload)})
        result.error = "max tool rounds exceeded without a final answer"
        result.answer = ""
        return result

    def _chat(self, messages: list[dict]) -> dict:
        response = self._http.post(
            "/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "tools": self._schema,
                "stream": False,
                "options": {"temperature": 0, "seed": 42},
            },
        )
        response.raise_for_status()
        return response.json()

    def _dispatch(self, name: str, args: dict) -> dict:
        method = getattr(self.tools, name, None)
        if method is None or name.startswith("_"):
            return {"error": f"unknown tool: {name}"}
        try:
            return method(**args)
        except ToolError as exc:
            return {"error": str(exc)}
        except TypeError as exc:
            return {"error": f"bad arguments for {name}: {exc}"}
