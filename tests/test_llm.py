import unittest
from dataclasses import dataclass

from brief import llm


@dataclass
class Fake:
    label: str
    answer: object = None
    error: Exception | None = None
    key: bool = True
    model: str = "fake-1"
    calls: int = 0

    def configured(self):
        return self.key

    def complete(self, system, user, schema):
        self.calls += 1
        if self.error:
            raise self.error
        return self.answer, self.model


def check(data):
    if not data.get("ok"):
        raise ValueError("not ok")
    return data


class ChainTest(unittest.TestCase):
    def test_first_good_answer_wins(self):
        a, b = Fake("Claude", {"ok": 1}), Fake("Gemini", {"ok": 1})
        out = llm.write([a, b], "s", "u", {}, check)
        self.assertEqual(out.writer, "fake-1 (Claude)")
        self.assertEqual(b.calls, 0)

    def test_falls_through_errors_bad_answers_and_missing_keys(self):
        chain = [Fake("Claude", error=TimeoutError("slow")), Fake("Gemini", {"ok": 0}), Fake("X", key=False), Fake("OpenAI", {"ok": 1})]
        out = llm.write(chain, "s", "u", {}, check)
        self.assertEqual(out.writer, "fake-1 (OpenAI)")
        self.assertEqual(len(out.failures), 3)
        self.assertIn("Claude: TimeoutError", out.failures[0])
        self.assertIn("Gemini: ValueError", out.failures[1])
        self.assertIn("no API key", out.failures[2])
        self.assertEqual(chain[2].calls, 0)

    def test_all_failing_gives_no_value(self):
        out = llm.write([Fake("Claude", error=RuntimeError("down"))], "s", "u", {}, check)
        self.assertIsNone(out.value)
        self.assertEqual(out.writer, "")

    def test_providers_are_in_order_claude_gemini_openai(self):
        from tests.helpers import cfg

        self.assertEqual([p.label for p in llm.providers(cfg())], ["Claude", "Gemini", "OpenAI"])


if __name__ == "__main__":
    unittest.main()
