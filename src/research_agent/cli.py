"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .agent import ResearchAgent
from .config import Settings, load_env_file
from .fetch import SafePageFetcher
from .search import OpenAIWebSearchBackend
from .source_store import SourceStore
from .tools import ToolRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a bounded, source validating web research agent.")
    parser.add_argument("question", nargs="*", help="Research question. If omitted, an interactive prompt is shown.")
    parser.add_argument("--trace", action="store_true", help="Print the tool trace after the answer.")
    parser.add_argument("--json", action="store_true", help="Print a machine readable result object.")
    parser.add_argument("--output", type=Path, help="Also save the result to this file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    parser = build_parser()
    args = parser.parse_args(argv)
    question = " ".join(args.question).strip()
    if not question:
        question = input("Research question: ").strip()
    if not question:
        parser.error("A research question is required.")
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is missing. Copy .env.example to .env and add your key.")

    try:
        from openai import OpenAI
    except ImportError:
        parser.error("The openai package is not installed. Run: python -m pip install -e .")

    settings = Settings.from_env()
    client = OpenAI()
    store = SourceStore()
    runtime = ToolRuntime(
        search_backend=OpenAIWebSearchBackend(client, settings.model),
        fetcher=SafePageFetcher(
            timeout_seconds=settings.fetch_timeout_seconds,
            max_bytes=settings.max_page_bytes,
            max_chars=settings.max_page_chars,
            max_redirects=settings.max_redirects,
        ),
        store=store,
        max_search_results=settings.max_search_results,
    )
    agent = ResearchAgent(
        client=client,
        model=settings.model,
        runtime=runtime,
        max_steps=settings.max_steps,
        max_model_retries=settings.max_model_retries,
    )
    result = agent.run(question)

    if args.json:
        rendered = json.dumps(
            {
                "answer": result.answer,
                "completed": result.completed,
                "stop_reason": result.stop_reason,
                "steps_used": result.steps_used,
                "trace": [event.as_dict() for event in result.trace],
                "sources": [source.public_dict(include_text=False) for source in result.sources],
            },
            ensure_ascii=False,
            indent=2,
        )
    else:
        rendered = result.answer
        if args.trace:
            rendered += f"\n## Tool trace ({result.steps_used}/{settings.max_steps} steps)\n\n{result.trace_markdown()}\n"

    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if result.completed else 2


if __name__ == "__main__":
    sys.exit(main())
