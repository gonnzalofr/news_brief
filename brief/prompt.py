"""What the model is asked, and the shape its answer must take. The same for every provider."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .feeds import Article

# How many pieces "For later" holds at most: analysis, opinion, long reads.
MAX_READS = 6

SYSTEM = """\
You are the editor of a personal morning news brief for one reader who wants to know what is \
happening in the world. You get the items several news outlets published since the last brief: \
for each, an id, its `source` (the outlet), its `access`, the sections it appeared in, the time, \
the headline and the standfirst (the outlet's one-line summary). You do not get the articles \
themselves.

`access` says whether the reader can open the article: "free" (anyone can), "unlocked" (the \
reader's subscription opens it; for the FT that is FT Edit, the FT editors' daily pick) or \
"paywalled" (the reader cannot open it).

The reader only gets what they can open. A paywalled item never has a place of its own: it can \
only go in the `also` list of a story whose `id` is free or unlocked. Use paywalled items to \
find what matters: when one reports something important, look for a free or unlocked item on \
the same event, from any outlet, and make that the story. When there is none, leave the \
story out.

Choose every story an informed reader of world news should know about this morning, judged on \
its news value alone: how much it matters and how interesting it is. No outlet gets a quota or \
a place because of its name. There is no maximum: a busy night gives a long brief, a quiet one a short brief. Leave out lifestyle, \
travel, food, fashion, property, puzzles, personal finance tips, sport and videos, unless a \
story matters beyond its own field. Leave out newsletters, live blogs and items that only list \
other stories.

The same event is often reported by several outlets, and more than once by one. Make it one \
story: put the item to link in `id` and the others in its `also` list. The item in `id` must be \
one the reader can open ("free" or "unlocked"); among those, take the most informative. Do not \
list an id twice anywhere in the answer.

Put each chosen item in exactly one place:
- `stories`: the news, most important first.
- `lines`: real news that matters less, worth one line (a court ruling, a deal, a datum).
- `reads`: analysis, opinion, columns and features worth reading later. At most {max_reads}. Choose \
a range: different subjects and outlets, not two pieces making the same argument.

The `id` of every story, line and read is free or unlocked; paywalled items appear only in \
`also`.

For every story, line and read, `source` is the `source` of its `id` item, exactly as given.

For each story:
- `headline`: the item's headline, lightly edited if needed so it reads as a plain sentence. \
Keep it short.
- `summary`: one to three plain sentences built only from the headline and standfirst of this \
item and the items in its `also` list. Never add facts, numbers or names they do not contain. \
Do not start with the headline's words. Do not name the outlets; the page shows them.
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
""".replace("{max_reads}", str(MAX_READS))

SCHEMA: dict = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "source": {"type": "string"},
                    "also": {"type": "array", "items": {"type": "string"}},
                    "headline": {"type": "string"},
                    "summary": {"type": "string"},
                    "weight": {"type": "integer", "enum": [2, 3, 4, 5]},
                    "topics": {"type": "array", "items": {"type": "string"}},
                    "place": {"type": "string"},
                },
                "required": ["id", "source", "also", "headline", "summary", "weight", "topics", "place"],
                "additionalProperties": False,
            },
        },
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "source": {"type": "string"}, "text": {"type": "string"}},
                "required": ["id", "source", "text"],
                "additionalProperties": False,
            },
        },
        "reads": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "source": {"type": "string"}, "note": {"type": "string"}},
                "required": ["id", "source", "note"],
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
Act as the editor described in `system`, for the items in `items` (the same id, source, \
access, sections, time, headline and standfirst a model would be sent). Answer with one JSON \
object that matches `schema` and nothing else: every key present, no other keys, each id used \
once and only ids from `items`, `source` equal to the source of its id, a free or unlocked id \
for every story, line and read (paywalled ids only in `also`), at least one story, `weight` 2 \
to 5, one to three `topics`, at most {max_reads} `reads`. Pass it on stdin to `python -m brief ingest --model <your \
name>`. If ingest lists problems, nothing was saved: fix them and run ingest again. If you \
cannot write the brief, run `python -m brief ingest --fallback` to send the outlets' own \
headlines instead.\
""".replace("{max_reads}", str(MAX_READS))


def _fmt(d: datetime, tz: ZoneInfo) -> str:
    return d.astimezone(tz).strftime("%a %d %b %H:%M")


def window_note(candidates: list[Article], tz: ZoneInfo, start: datetime, end: datetime) -> str:
    outlets = len({a.source for a in candidates})
    return (
        f"The brief covers {_fmt(start, tz)} to {_fmt(end, tz)} ({tz.key} time). "
        f"{len(candidates)} items from {outlets} outlet{'' if outlets == 1 else 's'} were published in that time"
    )


def access_note(a: Article) -> str:
    """The access line a model is sent: "unlocked (FT Edit)"."""
    return f"{a.access} ({a.via})" if a.via else a.access


def user_message(candidates: list[Article], tz: ZoneInfo, start: datetime, end: datetime) -> str:
    head = window_note(candidates, tz, start, end) + ":\n\n"
    rows = [
        f"id: {a.id}\nsource: {a.source}\naccess: {access_note(a)}\nsections: {', '.join(a.sections)}\n"
        f"time: {_fmt(a.published, tz)}\nheadline: {a.title}\nstandfirst: {a.standfirst or '(none)'}"
        for a in candidates
    ]
    return head + "\n\n".join(rows)
