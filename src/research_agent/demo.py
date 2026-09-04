"""Generate deterministic example runs without API keys or network access."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent import ResearchAgent
from .fetch import FetchError, StaticPageFetcher
from .models import FetchedPage, RunResult, SearchResult
from .search import StaticSearchBackend
from .source_store import SourceStore
from .tools import ToolRuntime


@dataclass(slots=True)
class _FunctionCall:
    name: str
    payload: dict[str, Any]
    call_id: str
    type: str = "function_call"

    @property
    def arguments(self) -> str:
        return json.dumps(self.payload)


@dataclass(slots=True)
class _Response:
    output: list[_FunctionCall]


class _ScriptedResponses:
    def __init__(self, calls: list[_FunctionCall]) -> None:
        self.calls = list(calls)

    def create(self, **kwargs) -> _Response:  # noqa: ANN003
        if not self.calls:
            raise RuntimeError("The demo planner ran out of scripted calls.")
        return _Response([self.calls.pop(0)])


class _ScriptedClient:
    def __init__(self, calls: list[_FunctionCall]) -> None:
        self.responses = _ScriptedResponses(calls)


def _call(index: int, name: str, payload: dict[str, Any]) -> _FunctionCall:
    return _FunctionCall(name=name, payload=payload, call_id=f"demo_call_{index}")


def _run(
    question: str,
    calls: list[_FunctionCall],
    results: dict[str, list[SearchResult]],
    pages: dict[str, FetchedPage | FetchError],
) -> RunResult:
    store = SourceStore()
    runtime = ToolRuntime(
        search_backend=StaticSearchBackend(results),
        fetcher=StaticPageFetcher(pages),
        store=store,
    )
    agent = ResearchAgent(
        client=_ScriptedClient(calls),
        model="offline_demo",
        runtime=runtime,
        max_steps=8,
        max_model_retries=0,
    )
    return agent.run(question)


def scenario_one() -> tuple[str, RunResult]:
    question = "How does an LLM function calling loop work?"
    query = "LLM function calling application loop"
    url = "https://developers.openai.com/api/docs/guides/function-calling"
    text = (
        "Tool calling is a multi step conversation between an application and a model. "
        "The application sends available tools, receives a tool call, executes the requested code, "
        "returns the tool output, and receives a final response or more tool calls. "
        "Strict mode improves adherence to the declared function schema."
    )
    calls = [
        _call(1, "search_web", {"query": query}),
        _call(2, "fetch_page", {"url": url}),
        _call(3, "summarize_sources", {"source_ids": ["S1"], "focus": "function calling loop and strict mode"}),
        _call(
            4,
            "submit_answer",
            {
                "title": "Function calling loop",
                "claims": [
                    {
                        "text": "Tool calling is an iterative conversation between a model and application code.",
                        "evidence": [
                            {
                                "source_id": "S1",
                                "quote": "Tool calling is a multi step conversation between an application and a model.",
                            }
                        ],
                    },
                    {
                        "text": "The application executes requested tools and returns their outputs before the model continues.",
                        "evidence": [
                            {
                                "source_id": "S1",
                                "quote": "The application sends available tools, receives a tool call, executes the requested code, returns the tool output, and receives a final response or more tool calls.",
                            }
                        ],
                    },
                ],
                "limitations": ["This offline demonstration uses a fixed page snapshot rather than live web access."],
            },
        ),
    ]
    return question, _run(
        question,
        calls,
        {query: [SearchResult("Function calling guide", url)]},
        {url: FetchedPage("Function calling guide", url, text)},
    )


def scenario_two() -> tuple[str, RunResult]:
    question = "What is the difference between inline search citations and a complete source list?"
    query = "web search inline citations sources field"
    url = "https://developers.openai.com/api/docs/guides/tools-web-search"
    text = (
        "Inline citations identify the most relevant references used in the answer. "
        "The sources field returns the complete list of URLs consulted during web search. "
        "The complete source list can therefore contain more URLs than the inline citation list."
    )
    calls = [
        _call(1, "search_web", {"query": query}),
        _call(2, "fetch_page", {"url": url}),
        _call(
            3,
            "submit_answer",
            {
                "title": "Inline citations versus the source list",
                "claims": [
                    {
                        "text": "Inline citations highlight the references most relevant to the displayed answer.",
                        "evidence": [
                            {
                                "source_id": "S1",
                                "quote": "Inline citations identify the most relevant references used in the answer.",
                            }
                        ],
                    },
                    {
                        "text": "A complete source list may include additional URLs consulted during search.",
                        "evidence": [
                            {
                                "source_id": "S1",
                                "quote": "The complete source list can therefore contain more URLs than the inline citation list.",
                            }
                        ],
                    },
                ],
                "limitations": ["This offline demonstration uses a fixed page snapshot rather than live web access."],
            },
        ),
    ]
    return question, _run(
        question,
        calls,
        {query: [SearchResult("Web search guide", url)]},
        {url: FetchedPage("Web search guide", url, text)},
    )


def scenario_three() -> tuple[str, RunResult]:
    question = "What does the unavailable report conclude?"
    query = "unavailable report conclusion"
    retry_query = "alternate source unavailable report"
    url = "https://example.com/unavailable_report"
    calls = [
        _call(1, "search_web", {"query": query}),
        _call(2, "fetch_page", {"url": url}),
        _call(3, "search_web", {"query": retry_query}),
        _call(
            4,
            "submit_answer",
            {
                "title": "Unable to verify the report",
                "claims": [],
                "limitations": [
                    "The discovered page timed out, and an alternative search returned no usable result; no factual conclusion is provided."
                ],
            },
        ),
    ]
    return question, _run(
        question,
        calls,
        {
            query: [SearchResult("Unavailable report", url)],
            retry_query: [],
        },
        {url: FetchError("network_error", "The page timed out.")},
    )


def scenarios() -> list[tuple[str, RunResult]]:
    return [scenario_one(), scenario_two(), scenario_three()]


def render_example(number: int, question: str, result: RunResult) -> str:
    return (
        f"# Example run {number}\n\n"
        "This transcript was generated by the deterministic offline demo using the same controller, "
        "tool runtime, source registry, step budget, and citation validator as production mode.\n\n"
        f"## Question\n\n{question}\n\n"
        f"## Tool trace ({result.steps_used}/8 steps)\n\n{result.trace_markdown()}\n\n"
        f"## Final answer\n\n{result.answer}\n"
        f"## Run status\n\n- Completed: `{str(result.completed).lower()}`\n"
        f"- Stop reason: `{result.stop_reason}`\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic offline examples.")
    parser.add_argument("--write_examples", type=Path, help="Write three Markdown transcripts to this directory.")
    args = parser.parse_args(argv)
    all_scenarios = scenarios()
    if args.write_examples:
        args.write_examples.mkdir(parents=True, exist_ok=True)
        names = ["run_1_success.md", "run_2_comparison.md", "run_3_failure_recovery.md"]
        for index, ((question, result), name) in enumerate(zip(all_scenarios, names), start=1):
            (args.write_examples / name).write_text(render_example(index, question, result), encoding="utf-8")
        print(f"Wrote {len(names)} example runs to {args.write_examples}")
    else:
        for index, (question, result) in enumerate(all_scenarios, start=1):
            print(render_example(index, question, result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
