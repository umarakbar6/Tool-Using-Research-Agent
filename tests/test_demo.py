from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent.demo import scenarios  # noqa: E402


class DemoTests(unittest.TestCase):
    def test_all_offline_scenarios_complete(self):
        runs = scenarios()
        self.assertEqual(len(runs), 3)
        self.assertTrue(all(result.completed for _, result in runs))
        self.assertEqual(len(runs[2][1].sources), 0)
        self.assertIn("no factual conclusion", runs[2][1].answer)


if __name__ == "__main__":
    unittest.main()
