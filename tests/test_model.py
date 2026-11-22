import unittest

from brief import render
from brief.model import Brief, digest, from_model, label, problems, related, without_model
from tests.helpers import art

CANDIDATES = [art(1, "Talks stall", 18), art(2, "Oil falls", 5), art(3, "Chip probe", 4), art(4, "A ruling", 3), art(5, "An essay", 2)]
ID = [a.id for a in CANDIDATES]


def story(i, weight=3, topics=("Energy",), **kw):
    return {"id": ID[i], "source": "FT", "also": [], "headline": f"Headline {i}", "summary": f"Summary {i}.", "weight": weight,
            "topics": list(topics), "place": "", **kw}


class FromModelTest(unittest.TestCase):
    def test_keeps_valid_items_and_sorts_by_weight(self):
        stories, lines, reads = from_model(
            {"stories": [story(1, 3), story(0, 5)], "lines": [{"id": ID[3], "text": "A court ruled."}],
             "reads": [{"id": ID[4], "note": "Why it matters."}]},
            CANDIDATES,
        )
        self.assertEqual([s.id for s in stories], [ID[0], ID[1]])
        self.assertEqual(stories[0].url, CANDIDATES[0].url)
        self.assertEqual(lines[0].text, "A court ruled.")
        self.assertEqual(reads[0].headline, "An essay")  # the FT's own headline for a read

    def test_drops_unknown_and_repeated_ids(self):
        stories, lines, _ = from_model(
            {"stories": [story(0), {**story(0), "headline": "again"}, {**story(1), "id": "made-up"}],
             "lines": [{"id": ID[0], "text": "repeat"}], "reads": []},
            CANDIDATES,
        )
        self.assertEqual([s.id for s in stories], [ID[0]])
        self.assertEqual(lines, [])

    def test_clamps_weight_and_trims_topics(self):
        stories, _, _ = from_model({"stories": [story(0, 9, ("AI", "ai", "EU", "Oil", "Tax"))], "lines": [], "reads": []}, CANDIDATES)
        self.assertEqual(stories[0].weight, 5)
        self.assertEqual(stories[0].topics, ["AI", "EU", "Oil"])

    def test_also_ids_become_links_and_are_used_up(self):
        stories, lines, _ = from_model(
            {"stories": [story(0, also=[ID[1], "nope"])], "lines": [{"id": ID[1], "text": "dup"}], "reads": []}, CANDIDATES
        )
        self.assertEqual([a.url for a in stories[0].also], [CANDIDATES[1].url])
        self.assertEqual(stories[0].also[0].label, "FT · paywalled")
        self.assertEqual(lines, [])

    def test_rejects_an_answer_with_no_usable_story(self):
        for bad in ([], "text", {"stories": [{"id": "x"}]}, {"stories": [{**story(0), "summary": ""}]}):
            with self.assertRaises(ValueError):
                from_model(bad, CANDIDATES)


class OtherTest(unittest.TestCase):
    def test_related_by_shared_topic_ignoring_case(self):
        stories, _, _ = from_model(
            {"stories": [story(0, 5, ("Energy",)), story(1, 4, ("energy", "Iran")), story(2, 3, ("AI",))], "lines": [], "reads": []},
            CANDIDATES,
        )
        self.assertEqual(related(stories), [[1], [0], []])

    def test_without_model_is_newest_first_with_no_weight(self):
        stories = without_model(CANDIDATES)
        self.assertEqual(stories[0].headline, "Talks stall")
        self.assertTrue(all(s.weight == 0 for s in stories))

    def test_brief_round_trips_through_a_dict(self):
        stories, lines, reads = from_model({"stories": [story(0)], "lines": [], "reads": []}, CANDIDATES)
        b = Brief("2026-11-22", "2026-11-22T07:00:00+01:00", "a", "b", 5, stories, lines, reads, "m (Claude)")
        self.assertEqual(Brief.from_dict(b.to_dict()), b)


# The same event from three outlets: the FT's report is paywalled, the BBC's free, an FT Edit piece unlocked.
MIXED = [art(1, "Talks stall", 18), art(2, "Talks stall, says BBC", 17, source="BBC", access="free"),
         art(3, "Why the talks stalled", 16, access="unlocked", via="FT Edit"), art(4, "Oil falls", 15, source="Guardian", access="free")]
MID = [a.id for a in MIXED]


def mixed(i, **kw):
    return {"id": MID[i], "source": MIXED[i].source, "also": [], "headline": f"Headline {i}", "summary": f"Summary {i}.",
            "weight": 3, "topics": ["Energy"], "place": "", **kw}


class SourcesTest(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(label("BBC", "free"), "BBC")
        self.assertEqual(label("FT", "unlocked", "FT Edit"), "FT Edit")
        self.assertEqual(label("FT", "paywalled"), "FT · paywalled")
        self.assertEqual(label("FT", ""), "FT")  # a brief from before 0.3.0

    def test_a_paywalled_story_links_the_readable_report_and_mentions_the_other(self):
        (s,), _, _ = from_model({"stories": [mixed(0, also=[MID[1]])], "lines": [], "reads": []}, MIXED)
        self.assertEqual((s.id, s.url, s.source, s.access, s.label), (MID[1], MIXED[1].url, "BBC", "free", "BBC"))
        self.assertEqual([(a.url, a.label) for a in s.also], [(MIXED[0].url, "FT · paywalled")])
        self.assertEqual(s.headline, "Headline 0")

    def test_source_and_access_come_from_the_items_not_the_answer(self):
        (s,), lines, reads = from_model({"stories": [mixed(2, source="Reuters")], "lines": [{"id": MID[3], "source": "x", "text": "Oil fell."}],
                                         "reads": [{"id": MID[0], "source": "FT", "note": "n"}]}, MIXED)
        self.assertEqual((s.source, s.label), ("FT", "FT Edit"))
        self.assertEqual((lines[0].source, lines[0].label), ("Guardian", "Guardian"))
        self.assertEqual(reads[0].label, "FT · paywalled")

    def test_problems_want_the_right_source_and_a_readable_id(self):
        answer = {"stories": [mixed(0, also=[MID[1]])], "lines": [{"id": MID[3], "source": "guardian", "text": "Oil fell."}],
                  "reads": [{"id": MID[2], "source": "BBC", "note": "n"}]}
        found = problems(answer, MIXED)
        self.assertIn("stories[0].id '" + MID[0] + "' is paywalled but also[0] (BBC, free) can be opened: make that one the id "
                      "and put the paywalled one in also", found)
        self.assertIn("reads[0].source must be 'FT', the source of its id, not 'BBC'", found)
        self.assertEqual(len(found), 2)  # case and spacing in a source don't matter
        del answer["lines"][0]["source"]
        self.assertIn("lines[0] has no 'source'", problems(answer, MIXED))
        fixed = {"stories": [mixed(1, also=[MID[0]])], "lines": [], "reads": [{"id": MID[2], "source": "FT", "note": "n"}]}
        self.assertEqual(problems(fixed, MIXED), [])

    def test_page_and_digest_show_the_outlet_of_every_item(self):
        stories, lines, reads = from_model({"stories": [mixed(1, also=[MID[0]]), mixed(2)], "lines": [{"id": MID[3], "source": "Guardian", "text": "Oil fell."}],
                                            "reads": []}, MIXED)
        b = Brief("2026-11-23", "2026-11-23T07:00:00+01:00", "2026-11-22T07:00:00+01:00", "2026-11-23T07:00:00+01:00", 4,
                  stories, lines, reads, "claude")
        page = render.brief_page(b, render.ZoneInfo("Europe/Amsterdam"))
        self.assertIn('<span class="src" title="Free to read">BBC</span>', page)
        self.assertIn('<span class="src open" title="Opens with your subscription">FT Edit</span>', page)
        self.assertIn(">Guardian</span>", page)
        self.assertIn(f'Also reported by <a href="{MIXED[0].url}" target="_blank" rel="noopener">FT · paywalled</a>', page)
        self.assertIn("from 3 outlets, 23 November", page)
        twice = from_model({"stories": [mixed(1, also=[MID[3], MID[0], MID[2]])], "lines": [], "reads": []},
                           MIXED + [art(5, "Oil, again", 14, source="Guardian", access="free")])[0][0]
        twice.also.append(twice.also[0])
        self.assertIn(f'Guardian (<a href="{MIXED[3].url}" target="_blank" rel="noopener">1</a>, '
                      f'<a href="{MIXED[3].url}" target="_blank" rel="noopener">2</a>), ', render._also(twice))
        self.assertIn('<link rel="icon" href="/favicon.svg" type="image/svg+xml">', page)
        self.assertIn('<link rel="apple-touch-icon" href="/apple-touch-icon.png">', page)
        d = digest(b)
        self.assertEqual((d["lead"]["source"], d["lead"]["label"]), ("BBC", "BBC"))
        self.assertEqual(d["lead"]["also"], [{"url": MIXED[0].url, "source": "FT", "access": "paywalled", "label": "FT · paywalled"}])
        self.assertEqual(d["lines"][0]["label"], "Guardian")

    def test_the_fallback_keeps_every_outlet_and_label(self):
        stories = without_model(MIXED)
        self.assertEqual([s.label for s in stories], ["FT · paywalled", "BBC", "FT Edit", "Guardian"])
        page = render.brief_page(Brief("2026-11-23", "2026-11-23T07:00:00+01:00", "2026-11-22T07:00:00+01:00", "2026-11-23T07:00:00+01:00", 4, stories, [], [], ""),
                                 render.ZoneInfo("Europe/Amsterdam"))
        self.assertIn('<span class="src shut" title="Paywalled: will not open in full">FT · paywalled</span>', page)
        self.assertIn("the outlets’ own headlines", page)

    def test_a_brief_from_before_sources_still_loads_and_shows_ft(self):
        old = {"date": "2026-11-21", "issued": "2026-11-21T23:27:00+01:00", "window_start": "2026-11-20T23:27:00+01:00", "window_end": "2026-11-21T23:27:00+01:00",
               "candidates": 2, "writer": "antigravity", "failures": [],
               "stories": [{"id": "x", "url": "https://www.ft.com/content/x", "headline": "H", "summary": "S", "weight": 3,
                            "topics": ["EU"], "place": "", "published": "2026-11-21T10:00:00+00:00", "also": ["https://www.ft.com/content/y"]}],
               "lines": [{"id": "z", "url": "https://www.ft.com/content/z", "text": "T", "published": "2026-11-21T10:00:00+00:00"}],
               "reads": []}
        b = Brief.from_dict(old)
        self.assertEqual((b.stories[0].label, b.stories[0].also[0].label, b.lines[0].label), ("FT", "FT", "FT"))
        self.assertEqual(Brief.from_dict(b.to_dict()), b)
        page = render.brief_page(b, render.ZoneInfo("Europe/Amsterdam"))
        self.assertIn("from the Financial Times, 21 November", page)
        self.assertIn('<span class="src">FT</span>', page)


if __name__ == "__main__":
    unittest.main()
