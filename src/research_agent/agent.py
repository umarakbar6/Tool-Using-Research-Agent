"""Bounded model/tool loop for the research agent."""

from __future__ import annotations

import json
import time
from typing import Any

from .models import RunResult, TraceEvent
from .prompts import RESEARCH_INSTRUCTIONS
from .schemas import TOOL_SCHEMAS
from .tools import ToolRuntime


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


class ResearchAgent:
    def __init__(
        self,
        *,
        client: Any,
        model: str,
        runtime: ToolRuntime,
        max_steps: int = 8,
        max_model_retries: int = 2,
    ) -> None:
        if max_steps < 2:
            raise ValueError("max_steps must be at least 2 so the agent can research and submit.")
        self.client = client
        self.model = model
        self.runtime = runtime
        self.max_steps = max_steps
        self.max_model_retries = max_model_retries

    def run(self, question: str) -> RunResult:
        question = " ".join(question.split()).strip()
        if not question:
            raise ValueError("A research question is required.")

        history: list[Any] = [{"role": "user", "content": question}]
        trace: list[TraceEvent] = []

        for step in range(1, self.max_steps + 1):
            last_step = step == self.max_steps
            tool_choice: Any = (
                {"type": "function", "name": "submit_answer"}
                if last_step
                else "auto"
            )

            try:
                response = self._request_model(history, tool_choice)
            except Exception as exc:
                trace.append(TraceEvent(step, "model_request", "error", self._short_error(exc)))
                continue

            output_items = list(_value(response, "output", []) or [])
            history.extend(output_items)
            function_calls = [item for item in output_items if _value(item, "type") == "function_call"]

            if not function_calls:
                trace.append(TraceEvent(step, "model_response", "retry", "Model returned text instead of a tool call."))
                history.append(
                    {
                        "role": "user",
                        "content": "Do not answer directly. Continue by calling one tool, or call submit_answer when ready.",
                    }
                )
                continue

            # parallel_tool_calls=False guarantees no more than one function call.
            call = function_calls[0]
            name = str(_value(call, "name", ""))
            call_id = str(_value(call, "call_id", ""))
            arguments: dict[str, Any] = {}
            try:
                arguments = json.loads(str(_value(call, "arguments", "{}")))
                if not isinstance(arguments, dict):
                    raise ValueError("Tool arguments must decode to an object.")
                result = self.runtime.dispatch(name, arguments)
            except Exception as exc:
                result = {
                    "ok": False,
                    "error": "tool_dispatch_failed",
                    "message": self._short_error(exc),
                    "retryable": True,
                }

            status = "ok" if result.get("ok") else "error"
            trace.append(TraceEvent(step, name or "unknown_tool", status, self._trace_detail(name, arguments, result)))

            if name == "submit_answer" and result.get("ok"):
                return RunResult(
                    answer=result["rendered_answer"],
                    completed=True,
                    stop_reason="answer_submitted",
                    steps_used=step,
                    trace=trace,
                    sources=self.runtime.store.all(),
                )

            history.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                }
            )

        return RunResult(
            answer=self._step_limit_answer(),
            completed=False,
            stop_reason="step_limit_reached",
            steps_used=self.max_steps,
            trace=trace,
            sources=self.runtime.store.all(),
        )

    def _request_model(self, history: list[Any], tool_choice: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_model_retries + 1):
            try:
                return self.client.responses.create(
                    model=self.model,
                    instructions=RESEARCH_INSTRUCTIONS,
                    input=history,
                    tools=TOOL_SCHEMAS,
                    tool_choice=tool_choice,
                    parallel_tool_calls=False,
                    max_output_tokens=1600,
                )
            except Exception as exc:
                last_error = exc
                if attempt < self.max_model_retries:
                    time.sleep(min(2**attempt, 2))
        assert last_error is not None
        raise last_error

    def _step_limit_answer(self) -> str:
        lines = [
            "# Research incomplete",
            "",
            f"I could not produce a fully source validated answer within the hard limit of {self.max_steps} model steps.",
        ]
        catalog = self.runtime.store.public_catalog()
        if catalog:
            lines.extend(["", "## Fetched sources", ""])
            lines.extend(f"- [{item['source_id']}] [{item['title']}]({item['url']})" for item in catalog)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _short_error(exc: Exception) -> str:
        return " ".join(str(exc).split())[:300] or type(exc).__name__

    @staticmethod
    def _trace_detail(name: str, arguments: dict[str, Any], result: dict[str, Any]) -> str:
        if name == "search_web":
            return f"query={arguments.get('query', '')!r}; results={len(result.get('results', []))}"
        if name == "fetch_page":
            suffix = result.get("source_id") or result.get("error", "unknown")
            return f"url={arguments.get('url', '')!r}; result={suffix}"
        if name == "summarize_sources":
            return f"sources={arguments.get('source_ids', [])!r}; status={result.get('ok', False)}"
        if name == "submit_answer":
            return f"claims={len(arguments.get('claims', []))}; status={result.get('ok', False)}"
        return str(result.get("error") or "completed")
