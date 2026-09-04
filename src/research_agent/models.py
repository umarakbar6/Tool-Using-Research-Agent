"""Small data models shared by the agent and its tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


@dataclass(frozen=True, slots=True)
class FetchedPage:
    title: str
    url: str
    text: str


@dataclass(frozen=True, slots=True)
class Source:
    source_id: str
    title: str
    url: str
    text: str

    def public_dict(self, *, include_text: bool = True) -> dict[str, str]:
        data = {"source_id": self.source_id, "title": self.title, "url": self.url}
        if include_text:
            data["text"] = self.text
        return data


@dataclass(frozen=True, slots=True)
class TraceEvent:
    step: int
    action: str
    status: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "action": self.action,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(slots=True)
class RunResult:
    answer: str
    completed: bool
    stop_reason: str
    steps_used: int
    trace: list[TraceEvent] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)

    def trace_markdown(self) -> str:
        if not self.trace:
            return "_No tool calls were recorded._"
        return "\n".join(
            f"{event.step}. `{event.action}` — **{event.status}** — {event.detail}"
            for event in self.trace
        )
