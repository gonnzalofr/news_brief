import unittest

from brief.model import Brief, from_model, related, without_model
from tests.helpers import art

CANDIDATES = [art(1, "Talks stall", 18), art(2, "Oil falls", 5), art(3, "Chip probe", 4), art(4, "A ruling", 3), art(5, "An essay", 2)]
ID = [a.id for a in CANDIDATES]


def story(i, weight=3, topics=("Energy",), **kw):
    return {"id": ID[i], "also": [], "headline": f"Headline {i}", "summary": f"Summary {i}.", "weight": weight,
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
        self.assertEqual(stories[0].also, [CANDIDATES[1].url])
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


if __name__ == "__main__":
    unittest.main()
