"""What the model is asked, and the shape its answer must take. The same for every provider."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .feeds import Article

SYSTEM = """\
You are the editor of a personal morning news brief for one reader, an FT subscriber who \
wants to know what is happening in the world. You get the FT stories published since the \
last brief: for each, an id, the FT sections it appeared in, the time, the headline and the \
standfirst (the FT's one-line summary). You do not get the articles themselves.

Choose every story an informed reader of world news should know about this morning. There \
is no maximum: a busy night gives a long brief, a quiet one a short brief. Leave out \
lifestyle, travel, food, fashion, property, puzzles, personal finance tips and sport, unless \
a story matters beyond its own field. Leave out newsletters that only list other stories.

When several items cover the same event, keep the most informative one and put the others' \
ids in its `also` list. Do not list an id twice anywhere in the answer.

Put each chosen item in exactly one place:
- `stories`: the news, most important first.
- `lines`: real news that matters less, worth one line (a court ruling, a deal, a datum).
- `reads`: analysis, opinion, columns and features worth reading later. At most four.

For each story:
- `headline`: the FT headline, lightly edited if needed so it reads as a plain sentence. \
Keep it short.
- `summary`: one to three plain sentences built only from the headline and standfirst of \
this item and the items in its `also` list. Never add facts, numbers or names they do not \
contain. Do not start with the headline's words.
- `weight`: 5 changes the course of world affairs, markets or a war for weeks; 4 is major \
news in its field; 3 is notable; 2 is worth knowing. Most stories are 2 or 3; keep 5 rare. \
Anything you would weigh 1 goes to `lines` instead.
- `topics`: one to three short subjects such as "AI", "Energy", "EU", "Ukraine", "Oil", \
"China", "US politics", "Latin America". Reuse the same words across stories that share a \
subject, so the brief can link them. Title case, no more than two words each.
- `place`: where it happens: a city, a country or a body of water. Use "" if there is no \
single place.

For each line: `text` is one sentence of news, at most 20 words. For each read: `note` is \
one sentence on what it argues or explains.

Write in British English, plainly, with no hype and no opinions of your own.\
"""

SCHEMA: dict = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "also": {"type": "array", "items": {"type": "string"}},
                    "headline": {"type": "string"},
                    "summary": {"type": "string"},
                    "weight": {"type": "integer", "enum": [2, 3, 4, 5]},
                    "topics": {"type": "array", "items": {"type": "string"}},
                    "place": {"type": "string"},
                },
                "required": ["id", "also", "headline", "summary", "weight", "topics", "place"],
                "additionalProperties": False,
            },
        },
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        },
        "reads": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "note": {"type": "string"}},
                "required": ["id", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["stories", "lines", "reads"],
    "additionalProperties": False,
}


# For an agent that writes the brief itself (`python -m brief fetch`, then `ingest`): what it
# does with SYSTEM, the items and SCHEMA. The editorial rules stay in SYSTEM, for every writer.
AGENT = """\
Act as the editor described in `system`, for the items in `items` (the same id, sections, \
time, headline and standfirst a model would be sent). Answer with one JSON object that \
matches `schema` and nothing else: every key present, no other keys, each id used once and \
only ids from `items`, at least one story, `weight` 2 to 5, one to three `topics`, at most \
four `reads`. Pass it on stdin to `python -m brief ingest --model <your name>`. If ingest \
lists problems, nothing was saved: fix them and run ingest again. If you cannot write the \
brief, run `python -m brief ingest --fallback` to send the FT's own headlines instead.\
"""


def _fmt(d: datetime, tz: ZoneInfo) -> str:
    return d.astimezone(tz).strftime("%a %d %b %H:%M")


def window_note(count: int, tz: ZoneInfo, start: datetime, end: datetime) -> str:
    return (
        f"The brief covers {_fmt(start, tz)} to {_fmt(end, tz)} ({tz.key} time). "
        f"{count} FT items were published in that time"
    )


def user_message(candidates: list[Article], tz: ZoneInfo, start: datetime, end: datetime) -> str:
    head = window_note(len(candidates), tz, start, end) + ":\n\n"
    rows = [
        f"id: {a.id}\nsections: {', '.join(a.sections)}\ntime: {_fmt(a.published, tz)}\n"
        f"headline: {a.title}\nstandfirst: {a.standfirst or '(none)'}"
        for a in candidates
    ]
    return head + "\n\n".join(rows)
