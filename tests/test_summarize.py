from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent.models import Source  # noqa: E402
from research_agent.summarize import summarize_sources  # noqa: E402


class SummarizerTests(unittest.TestCase):
    def test_returns_exact_relevant_passage(self):
        passage = "A hard step budget prevents an autonomous agent from looping indefinitely."
        source = Source("S1", "Agent safety", "https://example.com", f"General introduction. {passage} Final note.")
        result = summarize_sources([source], "step budget looping")
        self.assertIn(passage, result[0]["evidence_passages"])


if __name__ == "__main__":
    unittest.main()
