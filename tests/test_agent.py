from __future__ import annotations

import json
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent.agent import ResearchAgent  # noqa: E402
from research_agent.fetch import StaticPageFetcher  # noqa: E402
from research_agent.models import FetchedPage, SearchResult  # noqa: E402
from research_agent.search import StaticSearchBackend  # noqa: E402
from research_agent.source_store import SourceStore  # noqa: E402
from research_agent.tools import ToolRuntime  # noqa: E402


@dataclass
class Call:
    name: str
    payload: dict
    call_id: str
    type: str = "function_call"

    @property
    def arguments(self):
        return json.dumps(self.payload)


@dataclass
class Response:
    output: list


class ScriptedResponses:
    def __init__(self, calls):
        self.calls = list(calls)
        self.kwargs = []

    def create(self, **kwargs):
        self.kwargs.append(kwargs)
        return Response([self.calls.pop(0)])


class Client:
    def __init__(self, calls):
        self.responses = ScriptedResponses(calls)


def runtime_for(url="https://example.com/page"):
    query = "test query"
    text = "A sufficiently long exact evidence sentence confirms the tested claim in this deterministic page."
    store = SourceStore()
    runtime = ToolRuntime(
        search_backend=StaticSearchBackend({query: [SearchResult("Test", url)]}),
        fetcher=StaticPageFetcher({url: FetchedPage("Test", url, text)}),
        store=store,
    )
    return runtime, query, text


class AgentTests(unittest.TestCase):
    def test_successful_multi_tool_run(self):
        runtime, query, text = runtime_for()
        calls = [
            Call("search_web", {"query": query}, "c1"),
            Call("fetch_page", {"url": "https://example.com/page"}, "c2"),
            Call(
                "submit_answer",
                {
                    "title": "Test answer",
                    "claims": [{"text": "The tested claim is supported.", "evidence": [{"source_id": "S1", "quote": text}]}],
                    "limitations": [],
                },
                "c3",
            ),
        ]
        client = Client(calls)
        result = ResearchAgent(client=client, model="test", runtime=runtime, max_steps=5, max_model_retries=0).run("Question?")
        self.assertTrue(result.completed)
        self.assertEqual(result.steps_used, 3)
        self.assertIn("[S1]", result.answer)
        self.assertEqual([event.action for event in result.trace], ["search_web", "fetch_page", "submit_answer"])

    def test_hard_step_limit(self):
        runtime, query, _ = runtime_for()
        calls = [Call("search_web", {"query": query}, f"c{i}") for i in range(4)]
        client = Client(calls)
        result = ResearchAgent(client=client, model="test", runtime=runtime, max_steps=4, max_model_retries=0).run("Question?")
        self.assertFalse(result.completed)
        self.assertEqual(result.steps_used, 4)
        self.assertEqual(result.stop_reason, "step_limit_reached")
        self.assertEqual(len(client.responses.kwargs), 4)
        self.assertEqual(client.responses.kwargs[-1]["tool_choice"], {"type": "function", "name": "submit_answer"})


if __name__ == "__main__":
    unittest.main()
