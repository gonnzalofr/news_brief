import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from brief import __main__ as cli
from brief import config, external, job, prompt, server
from brief.model import problems
from brief.store import Store
from tests.helpers import cfg
from tests.test_job import ANSWER, ARTICLES

TZ = ZoneInfo("Europe/Amsterdam")
NOW = datetime(2026, 11, 22, 7, 0, tzinfo=TZ)  # a Sunday
IDS = [a.id for a in ARTICLES]


def fake_fetch(_sections):
    return list(ARTICLES), ["markets: timed out"]


class ExternalTest(unittest.TestCase):
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

    def fetch(self, articles=fake_fetch):
        return external.fetch(self.cfg, self.store, now=NOW, fetch=articles, send=self.send)

    def ingest(self, answer, **kw):
        text = answer if isinstance(answer, str) or answer is None else json.dumps(answer)
        return external.ingest(self.cfg, self.store, text, now=NOW, send=self.send, **kw)

    def test_fetch_gives_the_window_items_instructions_and_keeps_them(self):
        out = self.fetch()
        self.assertEqual(out["brief"]["date"], "2026-11-22")
        self.assertTrue(out["brief"]["weekend"])
        self.assertEqual(out["brief"]["window_start"], "2026-11-21T07:00:00+01:00")  # the first brief: 24 hours
        self.assertEqual(out["brief"]["feed_errors"], ["markets: timed out"])
        self.assertEqual([i["id"] for i in out["items"]], IDS[:2])  # the one from the 19th is outside the window
        item = out["items"][0]
        self.assertEqual(set(item), {"id", "headline", "standfirst", "sections", "url", "published"})
        self.assertEqual(out["instructions"]["system"], prompt.SYSTEM)
        self.assertEqual(out["instructions"]["schema"], prompt.SCHEMA)
        self.assertIn("2 FT items", out["instructions"]["context"])
        pending = json.loads(self.store.pending_path.read_text(encoding="utf-8"))
        self.assertEqual(pending["items"], out["items"])
        self.assertEqual(self.pushes, [])

    def test_fetch_with_every_feed_failing_raises_and_pushes(self):
        with self.assertRaises(job.NoFeeds):
            self.fetch(lambda _: ([], ["world: down"]))
        self.assertEqual(self.pushes[0][0], "Morning brief failed")
        self.assertFalse(self.store.pending_path.exists())

    def test_ingest_publishes_a_valid_answer_and_clears_pending(self):
        self.fetch()
        brief, pushed = self.ingest(ANSWER, writer="claude")
        self.assertTrue(pushed)
        self.assertEqual(brief.writer, "claude")
        self.assertEqual([s.id for s in brief.stories], IDS[:2])
        self.assertEqual(brief.failures, ["feed markets: timed out"])
        self.assertEqual(self.store.load("2026-11-22"), brief)
        self.assertEqual(self.store.state()["last_success"], "2026-11-22T07:00:00+01:00")  # so /readyz is ready
        self.assertFalse(self.store.pending_path.exists())
        self.assertIn("• Talks <b>stall</b>", self.pushes[0][1])

    def test_ingest_takes_a_fenced_answer_a_date_and_a_default_writer(self):
        self.fetch()
        brief, pushed = self.ingest("```json\n" + json.dumps(ANSWER) + "\n```", day="2026-11-23", push=False)
        self.assertFalse(pushed)
        self.assertEqual((brief.date, brief.writer), ("2026-11-23", external.DEFAULT_WRITER))
        self.assertEqual(self.pushes, [])

    def test_ingest_rejects_an_invalid_answer_saying_why_and_keeps_pending(self):
        self.fetch()
        bad = json.loads(json.dumps(ANSWER))
        bad["stories"][0]["weight"] = 7
        bad["stories"][1]["id"] = "made-up"
        del bad["stories"][1]["summary"]
        bad["lines"] = [{"id": IDS[0], "text": "again"}]
        with self.assertRaises(external.Invalid) as ctx:
            self.ingest(bad)
        found = ctx.exception.problems
        self.assertIn("stories[0].weight must be one of 2, 3, 4, 5, not 7", found)
        self.assertIn("stories[1] has no 'summary'", found)
        self.assertIn("stories[1].id 'made-up' is not the id of any item", found)
        self.assertTrue(any(p.startswith("lines[0].id") and "already used at stories[0].id" in p for p in found))
        self.assertTrue(self.store.pending_path.exists())
        self.assertEqual(self.store.dates(), [])
        self.assertEqual(self.pushes, [])

    def test_ingest_rejects_text_that_is_not_json(self):
        self.fetch()
        for text, expect in (("{stories:", "not valid JSON"), ("", "empty"), ("[]", "JSON object")):
            with self.assertRaises(external.Invalid) as ctx:
                self.ingest(text)
            self.assertIn(expect, ctx.exception.problems[0])

    def test_ingest_without_a_fetch_fails_clearly(self):
        with self.assertRaises(external.NoPending) as ctx:
            self.ingest(ANSWER)
        self.assertIn("run `python -m brief fetch` first", str(ctx.exception))

    def test_ingest_fallback_sends_the_ft_headlines(self):
        self.fetch()
        brief, _ = self.ingest(None, writer="claude", fallback=True)
        self.assertEqual(brief.writer, "")
        self.assertEqual([s.headline for s in brief.stories], ["Talks stall", "Oil falls"])
        self.assertIn("No model could write it", self.pushes[0][1])
        self.assertFalse(self.store.pending_path.exists())

    def test_the_next_fetch_starts_where_the_ingested_brief_ended(self):
        self.fetch()
        self.ingest(ANSWER)
        out = external.fetch(self.cfg, self.store, now=NOW.replace(day=23), fetch=fake_fetch, send=self.send)
        self.assertEqual(out["brief"]["window_start"], "2026-11-22T07:00:00+01:00")


class ProblemsTest(unittest.TestCase):
    def test_an_answer_that_follows_the_rules_has_none(self):
        self.assertEqual(problems(ANSWER, ARTICLES), [])

    def test_lists_shape_and_rule_problems(self):
        answer = {"stories": [], "lines": "none", "extra": 1}
        found = problems(answer, ARTICLES)
        self.assertIn("unknown top-level key 'extra': the answer has only stories, lines and reads", found)
        self.assertIn("lines must be a list, not a string", found)
        self.assertIn("'reads' is missing: use [] when there are none", found)
        self.assertIn("stories is empty: a brief needs at least one story", found)

    def test_topics_also_and_reads(self):
        story = {**ANSWER["stories"][0], "topics": [], "also": [IDS[0]], "headline": " "}
        reads = [{"id": i, "note": "n"} for i in IDS[1:]] + [{"id": "x", "note": "n"}] * 3
        found = problems({"stories": [story], "lines": [], "reads": reads}, ARTICLES)
        self.assertIn("stories[0].topics must hold one to three topics, not 0", found)
        self.assertIn("stories[0].headline is empty", found)
        self.assertTrue(any(p.startswith("stories[0].also[0]") and "already used" in p for p in found))
        self.assertIn("reads holds 5 items; at most four", found)


class CliTest(unittest.TestCase):
    """The commands as the agent runs them, through `python -m brief`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"DATA_DIR": self.tmp.name, "TZ": "Europe/Amsterdam", "NTFY_URL": "", "BRIEF_URL": "https://brief.example"}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.feeds = mock.patch("brief.feeds.fetch", fake_fetch)
        self.feeds.start()

    def tearDown(self):
        self.feeds.stop()
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, *argv, stdin=""):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), mock.patch("sys.stdin", io.StringIO(stdin)):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_fetch_ingest_latest(self):
        code, out, _ = self.run_cli("fetch")
        self.assertEqual(code, 0)
        items = json.loads(out)["items"]
        self.assertEqual(len(items), 2)

        answer = {"stories": [{"id": items[0]["id"], "also": [], "headline": "Talks stall", "summary": "They stalled.",
                               "weight": 4, "topics": ["Energy"], "place": "Antalya"}], "lines": [], "reads": []}
        code, out, _ = self.run_cli("ingest", "--model", "antigravity", stdin=json.dumps(answer))
        self.assertEqual(code, 0)
        summary = json.loads(out)
        self.assertEqual((summary["ok"], summary["stories"], summary["writer"]), (True, 1, "antigravity"))
        self.assertEqual(summary["top_headlines"], ["Talks stall"])
        self.assertFalse(summary["pushed"])  # no NTFY_URL

        code, out, _ = self.run_cli("latest", "--json")
        self.assertEqual(code, 0)
        latest = json.loads(out)
        self.assertEqual(latest["lead"]["headline"], "Talks stall")
        self.assertEqual(latest["lead"]["summary"], "They stalled.")
        self.assertEqual(latest["page"], f"https://brief.example/{latest['date']}")

    def test_fetch_to_a_file_and_ingest_from_one(self):
        path = Path(self.tmp.name) / "fetch.json"
        code, out, _ = self.run_cli("fetch", "--output", str(path))
        self.assertEqual((code, out), (0, ""))
        items = json.loads(path.read_text(encoding="utf-8"))["items"]
        answer = Path(self.tmp.name) / "answer.json"
        answer.write_text(json.dumps({"stories": [{"id": items[1]["id"], "also": [], "headline": "Oil falls", "summary": "It fell.",
                                                   "weight": 2, "topics": ["Oil"], "place": ""}], "lines": [], "reads": []}))
        code, out, _ = self.run_cli("ingest", "--input", str(answer), "--date", "2026-11-22", "--no-push")
        self.assertEqual((code, json.loads(out)["date"]), (0, "2026-11-22"))

    def test_invalid_answer_exits_non_zero_with_the_problems(self):
        self.run_cli("fetch")
        code, out, err = self.run_cli("ingest", stdin=json.dumps({"stories": [{"id": "nope"}], "lines": [], "reads": []}))
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out)["ok"])
        self.assertIn("- stories[0].id 'nope' is not the id of any item", err)
        self.assertIn("run ingest again", err)
        self.assertTrue((Path(self.tmp.name) / "pending.json").exists())

    def test_ingest_without_pending_and_latest_without_a_brief_fail(self):
        code, _, err = self.run_cli("ingest", stdin="{}")
        self.assertEqual(code, 1)
        self.assertIn("pending.json", err)
        self.assertEqual(self.run_cli("latest", "--json")[0], 1)

    def test_fallback_needs_no_answer(self):
        self.run_cli("fetch")
        code, out, _ = self.run_cli("ingest", "--fallback")
        self.assertEqual((code, json.loads(out)["writer"]), (0, ""))


class ModeTest(unittest.TestCase):
    def test_external_mode_starts_no_scheduler(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = cfg(tmp, BRIEF_MODE="external")
            self.assertEqual(c.mode, "external")
            self.assertIsNone(cli.start_scheduler(c, Store(c.data_dir), threading.Event()))
            stop = threading.Event()
            stop.set()  # the loop sees it at once and ends
            with mock.patch("brief.scheduler.due_now", return_value=False):
                worker = cli.start_scheduler(cfg(tmp), Store(c.data_dir), stop)
                self.assertIsNotNone(worker)
                worker.join(2)
                self.assertFalse(worker.is_alive())

    def test_mode_is_internal_unless_set_and_checked(self):
        self.assertEqual(cfg().mode, "internal")
        with self.assertRaises(config.ConfigError):
            cfg(BRIEF_MODE="sometimes")


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = cfg(self.tmp.name, HOST="127.0.0.1", PORT="0", BRIEF_MODE="external")
        self.store = Store(self.cfg.data_dir)
        self.httpd = server.serve(self.cfg, self.store)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                return r.status, r.headers.get("Content-Type"), r.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get("Content-Type"), exc.read()

    def test_latest_json_readyz_and_pages(self):
        self.assertEqual(self.get("/api/latest.json")[0], 404)
        self.assertEqual(self.get("/readyz")[0], 503)
        external.fetch(self.cfg, self.store, now=datetime.now(TZ), fetch=lambda _: ([a for a in ARTICLES], []), push=False)
        # The articles are from 21 Nov, so the window may hold none: the brief goes out either way.
        external.ingest(self.cfg, self.store, json.dumps(ANSWER), push=False, fallback=True)
        status, ctype, body = self.get("/api/latest.json")
        self.assertEqual((status, ctype), (200, "application/json"))
        self.assertIn("top_headlines", json.loads(body))
        self.assertEqual(self.get("/readyz")[0], 200)
        self.assertEqual(self.get("/healthz")[0], 200)
        self.assertEqual(self.get("/")[0], 200)


if __name__ == "__main__":
    unittest.main()
