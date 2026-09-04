"""In memory ledger for discovered URLs and fetched evidence."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from .models import SearchResult, Source


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    port = parts.port
    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    netloc = hostname if not port or default_port else f"{hostname}:{port}"
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


class SourceStore:
    """Tracks which URLs were discovered and which pages were fetched.

    Only fetched pages receive source IDs. Search snippets are deliberately not
    stored as evidence.
    """

    def __init__(self) -> None:
        self._candidates: dict[str, SearchResult] = {}
        self._sources: dict[str, Source] = {}
        self._source_by_url: dict[str, str] = {}

    def register_candidates(self, results: list[SearchResult]) -> None:
        for result in results:
            self._candidates[normalize_url(result.url)] = result

    def is_candidate(self, url: str) -> bool:
        return normalize_url(url) in self._candidates

    def candidate(self, url: str) -> SearchResult | None:
        return self._candidates.get(normalize_url(url))

    def add_source(self, *, title: str, url: str, text: str) -> Source:
        normalized = normalize_url(url)
        existing_id = self._source_by_url.get(normalized)
        if existing_id:
            return self._sources[existing_id]

        source_id = f"S{len(self._sources) + 1}"
        source = Source(
            source_id=source_id,
            title=title.strip() or normalized,
            url=normalized,
            text=text.strip(),
        )
        self._sources[source_id] = source
        self._source_by_url[normalized] = source_id
        return source

    def get(self, source_id: str) -> Source | None:
        return self._sources.get(source_id)

    def all(self) -> list[Source]:
        return list(self._sources.values())

    def public_catalog(self) -> list[dict[str, str]]:
        return [source.public_dict(include_text=False) for source in self.all()]
