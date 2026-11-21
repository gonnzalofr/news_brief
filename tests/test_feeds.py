import unittest
from datetime import datetime, timezone

from brief import feeds
from tests.helpers import RSS


class ParseTest(unittest.TestCase):
    def test_reads_items_and_skips_ones_without_a_date(self):
        items = feeds.parse_feed(RSS, "world")
        self.assertEqual(len(items), 2)
        a = items[0]
        self.assertEqual(a.id, "11111111-1111-1111-1111-111111111111")
        self.assertEqual(a.url, "https://www.ft.com/content/11111111-1111-1111-1111-111111111111")
        self.assertEqual(a.title, "Ministers agree ‘a deal’ on grain")
        self.assertEqual(a.standfirst, "The accord covers shipping through the Black Sea")
        self.assertEqual(a.published, datetime(2026, 11, 21, 18, 7, 2, tzinfo=timezone.utc))

    def test_merge_keeps_one_per_id_with_every_section(self):
        merged = feeds.merge(feeds.parse_feed(RSS, "world") + feeds.parse_feed(RSS, "markets"))
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].sections, ["world", "markets"])

    def test_fetch_survives_a_failing_feed(self):
        def download(url):
            if "markets" in url:
                raise OSError("timed out")
            return RSS

        articles, errors = feeds.fetch(["world", "markets"], download)
        self.assertEqual(len(articles), 2)
        self.assertEqual(len(errors), 1)
        self.assertIn("markets", errors[0])

    def test_window_is_open_at_the_start_closed_at_the_end(self):
        items = feeds.parse_feed(RSS, "world")
        start = datetime(2026, 11, 21, 5, 0, tzinfo=timezone.utc)
        end = datetime(2026, 11, 21, 18, 7, 2, tzinfo=timezone.utc)
        self.assertEqual([a.title for a in feeds.in_window(items, start, end)], ["Ministers agree ‘a deal’ on grain"])


if __name__ == "__main__":
    unittest.main()
