"""Search backends. The production backend uses OpenAI hosted web search."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol
from urllib.parse import urlsplit

from .models import SearchResult


class SearchBackend(Protocol):
    def search(self, query: str, max_results: int) -> list[SearchResult]: ...


def _as_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _walk(value: Any) -> Iterator[dict[str, Any]]:
    value = _as_plain(value)
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk(child)


class OpenAIWebSearchBackend:
    """Expose hosted web search as the agent's application side search tool."""

    def __init__(self, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        response = self.client.responses.create(
            model=self.model,
            tools=[{"type": "web_search"}],
            tool_choice="auto",
            include=["web_search_call.action.sources"],
            max_tool_calls=2,
            input=(
                "Use web search for this query. Return concise findings and make "
                f"relevant source URLs available. Query: {query}"
            ),
        )

        found: dict[str, SearchResult] = {}
        for node in _walk(response):
            url = node.get("url")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                continue
            title = node.get("title")
            if not isinstance(title, str) or not title.strip():
                title = urlsplit(url).hostname or url
            snippet = node.get("snippet") or node.get("text") or ""
            if not isinstance(snippet, str):
                snippet = ""
            found.setdefault(
                url,
                SearchResult(title=title.strip(), url=url, snippet=snippet[:500].strip()),
            )
            if len(found) >= max_results:
                break
        return list(found.values())


class StaticSearchBackend:
    """Deterministic backend used by tests and offline demonstration scripts."""

    def __init__(self, results_by_query: dict[str, list[SearchResult]]) -> None:
        self.results_by_query = results_by_query

    def search(self, query: str, max_results: int) -> list[SearchResult]:
        return list(self.results_by_query.get(query, []))[:max_results]
