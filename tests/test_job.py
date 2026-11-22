import json
import tempfile
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from brief import job, render, scheduler
from brief.store import Store
from tests.helpers import art, cfg
from tests.test_llm import Fake

TZ = ZoneInfo("Europe/Amsterdam")
NOW = datetime(2026, 11, 22, 7, 0, tzinfo=TZ)
ARTICLES = [art(1, "Talks stall", 18), art(2, "Oil falls", 8), art(3, "Old news", 1, day=19)]
ANSWER = {
    "stories": [
        {"id": ARTICLES[0].id, "source": "FT", "also": [], "headline": "Talks <b>stall</b>", "summary": "The talks stalled.", "weight": 5,
         "topics": ["Energy"], "place": "Antalya"},
        {"id": ARTICLES[1].id, "source": "FT", "also": [], "headline": "Oil falls", "summary": "Oil fell.", "weight": 4,
         "topics": ["Energy", "Oil"], "place": ""},
    ],
    "lines": [], "reads": [],
}


class JobTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = cfg(self.tmp.name, NTFY_URL="https://ntfy.example/topic", BRIEF_URL="https://brief.example")
        self.store = Store(self.cfg.data_dir)
        self.pushes = []

    def tearDown(self):
        self.tmp.cleanup()

    def send(self, url, token, title, message, **kw):
        self.pushes.append((title, message, kw))
        return True

    def run_job(self, chain, articles=ARTICLES, errors=()):
        return job.run(self.cfg, self.store, now=NOW, fetch=lambda _: (list(articles), list(errors)), chain=chain, send=self.send)

    def test_writes_saves_and_pushes(self):
        b = self.run_job([Fake("Claude", error=RuntimeError("down")), Fake("Gemini", ANSWER)])
        self.assertEqual(b.writer, "fake-1 (Gemini)")
        self.assertEqual(b.candidates, 2)  # the one from the 19th is outside the first 24 hours
        self.assertEqual(self.store.load("2026-11-22"), b)
        title, message, kw = self.pushes[0]
        self.assertIn("Sun 22 Nov", title)
        self.assertIn("• Talks <b>stall</b>", message)
        self.assertEqual(kw["click"], "https://brief.example/2026-11-22")
        self.assertEqual(self.store.state()["last_writer"], "fake-1 (Gemini)")

    def test_no_model_still_gives_a_brief_of_headlines(self):
        b = self.run_job([Fake("Claude", error=RuntimeError("down"))])
        self.assertEqual(b.writer, "")
        self.assertEqual([s.headline for s in b.stories], ["Talks stall", "Oil falls"])
        self.assertIn("No model could write it", self.pushes[0][1])
        self.assertEqual(self.pushes[0][2]["priority"], 4)

    def test_new_ft_edit_picks_join_the_brief_once_even_when_published_before_the_window(self):
        pick = art(4, "An FT Edit pick", 5, day=20, access="unlocked", via="FT Edit")  # two days old
        articles = [*ARTICLES, pick]
        b = self.run_job([Fake("Claude", ANSWER)], articles=articles)
        self.assertEqual(b.candidates, 3)  # the two in the window, and the pick
        self.assertEqual(self.store.state()["unlocked_seen"], [pick.id])
        later = job.run(self.cfg, self.store, now=NOW + timedelta(days=1), fetch=lambda _: (list(articles), []),
                        chain=[Fake("Claude", error=RuntimeError("down"))], send=self.send)
        self.assertEqual(later.candidates, 0)  # nothing new in the window, and the pick was already offered

    def test_every_feed_failing_raises_and_says_so(self):
        with self.assertRaises(job.NoFeeds):
            self.run_job([Fake("Claude", ANSWER)], articles=[], errors=["world: timed out"])
        self.assertEqual(self.pushes[0][0], "Morning brief failed")

    def test_next_window_starts_where_the_last_one_ended(self):
        self.run_job([Fake("Claude", ANSWER)])
        start, end = job.window(self.store, self.cfg, NOW + timedelta(days=1))
        self.assertEqual(start, NOW)

    def test_page_escapes_model_text_and_links_related_stories(self):
        b = self.run_job([Fake("Claude", ANSWER)])
        page = render.brief_page(b, TZ)
        self.assertIn("Talks &lt;b&gt;stall&lt;/b&gt;", page)
        self.assertNotIn("<b>stall", page)
        self.assertIn('href="#s2"', page)  # both are about Energy
        self.assertIn('aria-label="Weight 5 of 5"', page)
        self.assertNotIn('class="tw"', page)
        self.assertIn('class="tw"', render.brief_page(b, TZ, tweaks=True))


class SchedulerTest(unittest.TestCase):
    def test_next_run_is_today_before_the_time_and_tomorrow_after(self):
        at = cfg().run_at
        self.assertEqual(scheduler.next_run(datetime(2026, 11, 22, 6, 59, tzinfo=TZ), at, TZ), datetime(2026, 11, 22, 7, 0, tzinfo=TZ))
        self.assertEqual(scheduler.next_run(datetime(2026, 11, 22, 7, 0, tzinfo=TZ), at, TZ), datetime(2026, 11, 23, 7, 0, tzinfo=TZ))

    def test_next_run_keeps_local_time_across_the_clock_change(self):
        at = cfg().run_at
        nxt = scheduler.next_run(datetime(2026, 3, 28, 8, 0, tzinfo=TZ), at, TZ)  # summer time starts on the 29th
        self.assertEqual((nxt.hour, nxt.utcoffset()), (7, timedelta(hours=2)))

    def test_catches_up_only_soon_after_and_only_once(self):
        at = cfg().run_at
        self.assertTrue(scheduler.due_now(datetime(2026, 11, 22, 9, 0, tzinfo=TZ), at, TZ, has_today=False))
        self.assertFalse(scheduler.due_now(datetime(2026, 11, 22, 9, 0, tzinfo=TZ), at, TZ, has_today=True))
        self.assertFalse(scheduler.due_now(datetime(2026, 11, 22, 12, 0, tzinfo=TZ), at, TZ, has_today=False))
        self.assertFalse(scheduler.due_now(datetime(2026, 11, 22, 6, 0, tzinfo=TZ), at, TZ, has_today=False))


class SampleTest(unittest.TestCase):
    def test_sample_brief_renders(self):
        from pathlib import Path

        from brief.model import Brief

        data = json.loads((Path(__file__).resolve().parent.parent / "samples" / "sample-brief.json").read_text(encoding="utf-8"))
        page = render.brief_page(Brief.from_dict(data), TZ)
        self.assertIn("For the weekend", page)  # 22 Nov 2026 is a Sunday
        self.assertIn("Sat 19:07", page)  # 18:07 GMT, shown in Amsterdam time


if __name__ == "__main__":
    unittest.main()
