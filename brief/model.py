"""The brief as data: what the page shows and what is stored, one JSON file a day."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from .feeds import Article


@dataclass
class Story:
    id: str
    url: str
    headline: str
    summary: str
    weight: int  # 2-5; 0 when no model wrote the brief
    topics: list[str]
    place: str
    published: str  # ISO 8601, UTC
    also: list[str] = field(default_factory=list)  # urls of other FT items on the same event


@dataclass
class Line:
    id: str
    url: str
    text: str
    published: str


@dataclass
class Read:
    id: str
    url: str
    headline: str
    note: str
    published: str


@dataclass
class Brief:
    date: str  # the local day it is for, YYYY-MM-DD
    issued: str  # ISO 8601 with offset
    window_start: str
    window_end: str
    candidates: int
    stories: list[Story]
    lines: list[Line]
    reads: list[Read]
    writer: str  # "claude-opus-5-5 (Claude)", or "" when no model could write it
    failures: list[str] = field(default_factory=list)  # one line per provider or feed that failed

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Brief":
        return cls(
            **{k: v for k, v in d.items() if k not in {"stories", "lines", "reads"}},
            stories=[Story(**s) for s in d.get("stories", [])],
            lines=[Line(**x) for x in d.get("lines", [])],
            reads=[Read(**r) for r in d.get("reads", [])],
        )


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def from_model(data: dict, candidates: list[Article]) -> tuple[list[Story], list[Line], list[Read]]:
    """Checks a model's answer against the articles it was given and keeps only what holds up.

    Unknown ids, repeats and empty text are dropped, weights are kept in 2-5 and topics to
    three. Raises ValueError when nothing usable is left, so the next provider gets a turn.
    """
    if not isinstance(data, dict):
        raise ValueError("answer is not a JSON object")
    by_id = {a.id: a for a in candidates}
    used: set[str] = set()

    def take(item_id: object) -> Article | None:
        if not isinstance(item_id, str) or item_id not in by_id or item_id in used:
            return None
        used.add(item_id)
        return by_id[item_id]

    def text(value: object) -> str:
        return " ".join(value.split()) if isinstance(value, str) else ""

    stories: list[Story] = []
    for s in data.get("stories") or []:
        if not isinstance(s, dict):
            continue
        a = take(s.get("id"))
        headline, summary = text(s.get("headline")) or (a.title if a else ""), text(s.get("summary"))
        if not a or not summary:
            continue
        try:
            weight = min(5, max(2, int(s.get("weight", 2))))
        except (TypeError, ValueError):
            weight = 2
        topics: list[str] = []
        for t in s.get("topics") or []:
            t = text(t)
            if t and t.lower() not in {x.lower() for x in topics}:
                topics.append(t)
        also = [by_id[x].url for x in (s.get("also") or []) if take(x)]
        stories.append(Story(a.id, a.url, headline, summary, weight, topics[:3], text(s.get("place")), iso(a.published), also))
    if not stories:
        raise ValueError("no usable stories in the answer")
    # Most important first; the model's own order breaks ties.
    stories.sort(key=lambda s: -s.weight)

    lines = [
        Line(a.id, a.url, text(x.get("text")), iso(a.published))
        for x in data.get("lines") or []
        if isinstance(x, dict) and text(x.get("text")) and (a := take(x.get("id")))
    ]
    reads = [
        Read(a.id, a.url, a.title, text(x.get("note")), iso(a.published))
        for x in data.get("reads") or []
        if isinstance(x, dict) and (a := take(x.get("id")))
    ][:4]
    return stories, lines, reads


def without_model(candidates: list[Article]) -> list[Story]:
    """When no model answers: every item as the FT wrote it, newest first, with no weights."""
    return [
        Story(a.id, a.url, a.title, a.standfirst, 0, [], "", iso(a.published))
        for a in sorted(candidates, key=lambda a: a.published, reverse=True)
    ]


def related(stories: list[Story]) -> list[list[int]]:
    """For each story, the indexes of the other stories that share a topic with it."""
    keys = [{t.lower() for t in s.topics} for s in stories]
    return [[j for j in range(len(stories)) if j != i and keys[i] & keys[j]] for i in range(len(stories))]
