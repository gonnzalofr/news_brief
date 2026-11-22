import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from brief import config, feeds
from brief.config import Source
from tests.helpers import ATOM, RSS

FT = Source("FT", (("world", "https://ft.example/world"), ("markets", "https://ft.example/markets")), "paywalled",
            "https://ft.example/ft-edit", "FT Edit")
TECH = Source("Tech Daily", (("all", "https://tech.example/feed"),))

# The FT Edit feed: the first item of RSS only, with the FT's tracking query.
EDIT = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>FT Edit</title>
<item><title>Ministers agree &#8216;a deal&#8217; on grain</title>
<link>https://www.ft.com/content/11111111-1111-1111-1111-111111111111?syn-25a6b1a6=1</link>
<description>The accord covers shipping through the Black Sea</description>
<pubDate>Sat, 21 Nov 2026 18:07:02 GMT</pubDate></item>
</channel></rss>"""


def downloader(fail: tuple[str, ...] = ()):
    def download(url):
        if any(f in url for f in fail):
            raise OSError("timed out")
        return {"https://ft.example/ft-edit": EDIT, "https://tech.example/feed": ATOM}.get(url, RSS)
    return download


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

    def test_reads_atom_and_cleans_other_outlets_links(self):
        items = feeds.parse_feed(ATOM, "all", "Tech Daily")
        self.assertEqual(len(items), 1)  # the entry with no link is left out
        a = items[0]
        self.assertEqual((a.id, a.url), ("https://tech.example/2026/11/21/merge",) * 2)
        self.assertEqual((a.title, a.standfirst, a.source), ("Chip maker & rival merge", "The deal is worth $5bn", "Tech Daily"))
        self.assertEqual(a.published, datetime(2026, 11, 21, 22, 30, tzinfo=timezone.utc))  # published, not updated

    def test_merge_keeps_one_per_id_with_every_section(self):
        merged = feeds.merge(feeds.parse_feed(RSS, "world") + feeds.parse_feed(RSS, "markets"))
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].sections, ["world", "markets"])

    def test_window_is_open_at_the_start_closed_at_the_end(self):
        items = feeds.parse_feed(RSS, "world")
        start = datetime(2026, 11, 21, 5, 0, tzinfo=timezone.utc)
        end = datetime(2026, 11, 21, 18, 7, 2, tzinfo=timezone.utc)
        self.assertEqual([a.title for a in feeds.in_window(items, start, end)], ["Ministers agree ‘a deal’ on grain"])


class FetchTest(unittest.TestCase):
    def test_marks_ft_edit_items_unlocked_the_other_ft_items_paywalled_and_free_outlets_free(self):
        articles, errors = feeds.fetch([FT, TECH], downloader())
        self.assertEqual(errors, [])
        by_title = {a.title: a for a in articles}
        edit = by_title["Ministers agree ‘a deal’ on grain"]
        self.assertEqual((edit.source, edit.access, edit.via, edit.readable), ("FT", "unlocked", "FT Edit", True))
        self.assertEqual(edit.sections, ["world", "markets", "FT Edit"])
        self.assertEqual(edit.url, "https://www.ft.com/content/11111111-1111-1111-1111-111111111111")
        shut = by_title["Central bank holds rates"]
        self.assertEqual((shut.access, shut.via, shut.readable), ("paywalled", "", False))
        self.assertEqual((by_title["Chip maker & rival merge"].source, by_title["Chip maker & rival merge"].access), ("Tech Daily", "free"))

    def test_without_the_ft_edit_feed_every_ft_item_counts_as_paywalled(self):
        articles, errors = feeds.fetch([FT], downloader(fail=("ft-edit",)))
        self.assertEqual(errors, ["FT FT Edit: timed out"])
        self.assertEqual({a.access for a in articles}, {"paywalled"})

    def test_fetch_survives_a_failing_feed(self):
        articles, errors = feeds.fetch([FT, TECH], downloader(fail=("markets", "tech.example")))
        self.assertEqual(len(articles), 2)
        self.assertEqual(errors, ["FT markets: timed out", "Tech Daily all: timed out"])

    def test_items_carry_source_and_access_through_pending(self):
        articles, _ = feeds.fetch([FT], downloader())
        a = articles[0]
        self.assertEqual(feeds.Article.from_dict(a.to_dict()), a)
        old = {k: v for k, v in a.to_dict().items() if k not in {"source", "access", "via"}}  # a 0.2.0 item
        self.assertEqual((feeds.Article.from_dict(old).source, feeds.Article.from_dict(old).access), ("FT", "paywalled"))


class SourcesTest(unittest.TestCase):
    def test_the_shipped_sources_load_with_ft_edit_for_the_ft(self):
        sources = config.load({"DATA_DIR": "/tmp"}).sources
        ft = next(s for s in sources if s.name == "FT")
        self.assertEqual((ft.access, ft.unlocked, ft.unlocked_label), ("paywalled", "https://www.ft.com/ft-edit?format=rss", "FT Edit"))
        self.assertGreaterEqual(len(sources), 5)
        self.assertTrue(all(s.access == "free" for s in sources if s.name != "FT"))
        names = {s.name for s in sources}
        self.assertLessEqual({"The Conversation", "VoxEU", "ProPublica", "Rest of World"}, names)  # analysis and opinion
        guardian = dict(next(s for s in sources if s.name == "Guardian").feeds)
        self.assertIn("opinion", guardian)
        self.assertTrue(all(url.startswith("https://") for s in sources for _, url in s.feeds))

    def test_sources_file_is_checked(self):
        cases = {
            '[[source]]\nname = "X"\naccess = "free"\n': "has no feeds",
            '[[source]]\nname = "X"\naccess = "metered"\n[source.feeds]\na = "https://x.example/rss"\n': "access must be",
            '[[source]]\nname = "X"\n[source.feeds]\na = "ftp://x.example/rss"\n': "must be a feed URL",
            '[[source]]\nname = "X"\nunlocked = "https://x.example/u"\n[source.feeds]\na = "https://x.example/rss"\n': "only for a paywalled",
            "": "lists no sources",
            "[[source": "can't read",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.toml"
            for text, expect in cases.items():
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(config.ConfigError) as ctx:
                    config.load({"DATA_DIR": tmp, "SOURCES_FILE": str(path)})
                self.assertIn(expect, str(ctx.exception))
            path.write_text('[[source]]\nname = "X"\n[source.feeds]\nall = "https://x.example/rss"\n', encoding="utf-8")
            (only,) = config.load({"DATA_DIR": tmp, "SOURCES_FILE": str(path)}).sources
            self.assertEqual((only.name, only.access, only.feeds), ("X", "free", (("all", "https://x.example/rss"),)))


if __name__ == "__main__":
    unittest.main()
