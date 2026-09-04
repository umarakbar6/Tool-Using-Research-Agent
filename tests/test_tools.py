from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent.fetch import FetchError, StaticPageFetcher, validate_public_url  # noqa: E402
from research_agent.models import FetchedPage, SearchResult  # noqa: E402
from research_agent.search import StaticSearchBackend  # noqa: E402
from research_agent.source_store import SourceStore  # noqa: E402
from research_agent.tools import ToolRuntime  # noqa: E402


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.query = "evidence query"
        self.url = "https://example.com/evidence"
        self.text = "This exact supporting passage is deliberately long enough for strict evidence validation."
        self.store = SourceStore()
        self.runtime = ToolRuntime(
            search_backend=StaticSearchBackend({self.query: [SearchResult("Evidence", self.url)]}),
            fetcher=StaticPageFetcher({self.url: FetchedPage("Evidence", self.url, self.text)}),
            store=self.store,
        )

    def fetch_source(self):
        self.runtime.search_web(self.query)
        result = self.runtime.fetch_page(self.url)
        self.assertTrue(result["ok"])

    def test_fetch_rejects_url_not_returned_by_search(self):
        result = self.runtime.fetch_page(self.url)
        self.assertEqual(result["error"], "url_not_discovered")

    def test_unknown_source_is_rejected(self):
        result = self.runtime.submit_answer(
            {
                "title": "Bad",
                "claims": [{"text": "Unsupported", "evidence": [{"source_id": "S99", "quote": self.text}]}],
                "limitations": [],
            }
        )
        self.assertFalse(result["ok"])
        self.assertIn("unknown source", " ".join(result["details"]))

    def test_quote_not_in_source_is_rejected(self):
        self.fetch_source()
        result = self.runtime.submit_answer(
            {
                "title": "Bad quote",
                "claims": [
                    {
                        "text": "Unsupported",
                        "evidence": [{"source_id": "S1", "quote": "This quotation is fabricated and is not present in the fetched page text."}],
                    }
                ],
                "limitations": [],
            }
        )
        self.assertFalse(result["ok"])
        self.assertIn("not found", " ".join(result["details"]))

    def test_exact_quote_is_accepted(self):
        self.fetch_source()
        result = self.runtime.submit_answer(
            {
                "title": "Good",
                "claims": [{"text": "Supported", "evidence": [{"source_id": "S1", "quote": self.text}]}],
                "limitations": [],
            }
        )
        self.assertTrue(result["ok"])
        self.assertIn(self.url, result["rendered_answer"])

    def test_fetch_failure_is_structured(self):
        store = SourceStore()
        runtime = ToolRuntime(
            search_backend=StaticSearchBackend({self.query: [SearchResult("Evidence", self.url)]}),
            fetcher=StaticPageFetcher({self.url: FetchError("network_error", "Timed out")}),
            store=store,
        )
        runtime.search_web(self.query)
        result = runtime.fetch_page(self.url)
        self.assertEqual(result["error"], "network_error")
        self.assertTrue(result["retryable"])

    def test_invalid_scheme_is_blocked(self):
        with self.assertRaises(FetchError) as context:
            validate_public_url("file:///etc/passwd")
        self.assertEqual(context.exception.code, "invalid_scheme")


if __name__ == "__main__":
    unittest.main()
