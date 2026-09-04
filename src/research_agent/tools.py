"""Application side tool implementations and final citation validation."""

from __future__ import annotations

from typing import Any

from .fetch import FetchError, PageFetcher
from .search import SearchBackend
from .source_store import SourceStore
from .summarize import summarize_sources


def _normalize_text(text: str) -> str:
    return " ".join(text.casefold().split())


def _clean_inline(text: str) -> str:
    return " ".join(str(text).replace("\n", " ").split()).strip()


class ToolRuntime:
    def __init__(
        self,
        *,
        search_backend: SearchBackend,
        fetcher: PageFetcher,
        store: SourceStore,
        max_search_results: int = 5,
    ) -> None:
        self.search_backend = search_backend
        self.fetcher = fetcher
        self.store = store
        self.max_search_results = max_search_results

    def dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "search_web":
            return self.search_web(arguments.get("query", ""))
        if name == "fetch_page":
            return self.fetch_page(arguments.get("url", ""))
        if name == "summarize_sources":
            return self.summarize(
                arguments.get("source_ids", []),
                arguments.get("focus", ""),
            )
        if name == "submit_answer":
            return self.submit_answer(arguments)
        return {
            "ok": False,
            "error": "unknown_tool",
            "message": f"No tool named {name!r} is available.",
            "retryable": False,
        }

    def search_web(self, query: str) -> dict[str, Any]:
        query = _clean_inline(query)
        if not query:
            return {"ok": False, "error": "empty_query", "message": "Search query is empty.", "retryable": True}
        try:
            results = self.search_backend.search(query, self.max_search_results)
            self.store.register_candidates(results)
        except Exception as exc:  # The agent needs structured failure data, never a crash.
            return {
                "ok": False,
                "error": "search_failed",
                "message": _clean_inline(str(exc)) or type(exc).__name__,
                "retryable": True,
            }
        return {
            "ok": True,
            "query": query,
            "results": [result.as_dict() for result in results],
            "warning": "Search results are discovery leads, not fetched evidence." if results else "No results were returned.",
        }

    def fetch_page(self, url: str) -> dict[str, Any]:
        url = str(url).strip()
        try:
            discovered = self.store.is_candidate(url)
        except Exception as exc:
            return {
                "ok": False,
                "error": "invalid_url",
                "message": _clean_inline(str(exc)) or "The URL is malformed.",
                "retryable": False,
            }
        if not discovered:
            return {
                "ok": False,
                "error": "url_not_discovered",
                "message": "fetch_page accepts only URLs previously returned by search_web.",
                "retryable": True,
            }
        try:
            page = self.fetcher.fetch(url)
        except FetchError as exc:
            return {
                "ok": False,
                "error": exc.code,
                "message": _clean_inline(str(exc)),
                "retryable": exc.retryable,
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": "fetch_failed",
                "message": _clean_inline(str(exc)) or type(exc).__name__,
                "retryable": True,
            }

        source = self.store.add_source(title=page.title, url=page.url, text=page.text)
        return {"ok": True, **source.public_dict(include_text=True)}

    def summarize(self, source_ids: list[str], focus: str) -> dict[str, Any]:
        if not isinstance(source_ids, list) or not source_ids:
            return {"ok": False, "error": "no_sources", "message": "At least one source ID is required.", "retryable": True}
        sources = []
        missing = []
        for source_id in source_ids:
            source = self.store.get(str(source_id))
            if source is None:
                missing.append(str(source_id))
            else:
                sources.append(source)
        if missing:
            return {
                "ok": False,
                "error": "unknown_sources",
                "message": f"Unknown fetched source IDs: {', '.join(missing)}",
                "retryable": True,
            }
        return {
            "ok": True,
            "focus": _clean_inline(focus),
            "summaries": summarize_sources(sources, focus),
        }

    def submit_answer(self, arguments: dict[str, Any]) -> dict[str, Any]:
        title = _clean_inline(arguments.get("title", ""))
        claims = arguments.get("claims", [])
        limitations = arguments.get("limitations", [])
        errors: list[str] = []

        if not title:
            errors.append("A non empty title is required.")
        if not isinstance(claims, list) or not isinstance(limitations, list):
            errors.append("claims and limitations must both be arrays.")
            claims = []
            limitations = []
        if not claims and not limitations:
            errors.append("Submit at least one supported claim or one research limitation.")
        if len(claims) > 20:
            errors.append("The answer contains more than 20 claims; make it more focused.")

        cited_ids: list[str] = []
        for index, claim in enumerate(claims, start=1):
            if not isinstance(claim, dict):
                errors.append(f"Claim {index} is not an object.")
                continue
            claim_text = _clean_inline(claim.get("text", ""))
            evidence = claim.get("evidence", [])
            if not claim_text:
                errors.append(f"Claim {index} has no text.")
            if not isinstance(evidence, list) or not evidence:
                errors.append(f"Claim {index} has no evidence.")
                continue
            for evidence_index, item in enumerate(evidence, start=1):
                if not isinstance(item, dict):
                    errors.append(f"Claim {index}, evidence {evidence_index} is not an object.")
                    continue
                source_id = _clean_inline(item.get("source_id", ""))
                quote = _clean_inline(item.get("quote", ""))
                source = self.store.get(source_id)
                if source is None:
                    errors.append(f"Claim {index} cites unknown source {source_id or '(empty)' }.")
                    continue
                if len(quote) < 20:
                    errors.append(f"Claim {index}, {source_id} has an evidence quote shorter than 20 characters.")
                    continue
                if _normalize_text(quote) not in _normalize_text(source.text):
                    errors.append(f"Claim {index} contains a quote not found in {source_id}.")
                    continue
                if source_id not in cited_ids:
                    cited_ids.append(source_id)

        if errors:
            return {
                "ok": False,
                "error": "citation_validation_failed",
                "message": "The submitted answer did not pass evidence validation.",
                "details": errors,
                "retryable": True,
            }

        rendered = self._render_answer(title, claims, limitations, cited_ids)
        return {
            "ok": True,
            "rendered_answer": rendered,
            "claim_count": len(claims),
            "cited_source_ids": cited_ids,
        }

    def _render_answer(
        self,
        title: str,
        claims: list[dict[str, Any]],
        limitations: list[str],
        cited_ids: list[str],
    ) -> str:
        lines = [f"# {title}", ""]
        for claim in claims:
            source_ids: list[str] = []
            for evidence in claim["evidence"]:
                source_id = _clean_inline(evidence["source_id"])
                if source_id not in source_ids:
                    source_ids.append(source_id)
            citation = "".join(f"[{source_id}]" for source_id in source_ids)
            lines.append(f"- {_clean_inline(claim['text'])} {citation}")
            for evidence in claim["evidence"]:
                quote = _clean_inline(evidence["quote"])
                lines.append(f"  - Evidence {evidence['source_id']}: “{quote}”")

        clean_limitations = [_clean_inline(item) for item in limitations if _clean_inline(item)]
        if clean_limitations:
            if lines[-1] != "":
                lines.append("")
            lines.extend(["## Limitations", ""])
            lines.extend(f"- {item}" for item in clean_limitations)

        if cited_ids:
            lines.extend(["", "## Sources", ""])
            for source_id in cited_ids:
                source = self.store.get(source_id)
                assert source is not None
                safe_title = source.title.replace("[", "\\[").replace("]", "\\]")
                lines.append(f"- [{source_id}] [{safe_title}]({source.url})")
        return "\n".join(lines).strip() + "\n"
