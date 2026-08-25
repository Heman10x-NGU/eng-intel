"""Unit tests for ingest data-quality flags."""

from __future__ import annotations

import unittest

from normalize import rss_entries


class DegradedIngestTest(unittest.TestCase):
    def test_unparseable_date_sets_degraded_ledger_flag(self) -> None:
        entries = [
            {
                "title": "Broken date post",
                "url": "https://example.com/broken",
                "published_at": "not-a-valid-date",
                "summary": "body",
            }
        ]
        docs, run = rss_entries("supabase", entries)
        self.assertEqual(len(docs), 1)
        self.assertIsNone(docs[0].published_at)
        self.assertEqual(run.n_rows, 1)
        self.assertIsNone(run.coverage_start)
        self.assertEqual(run.degraded, 1)
        self.assertIn("unparseable", (run.note or "").lower())


if __name__ == "__main__":
    unittest.main()
