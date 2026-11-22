"""The brief as data: what the page shows and what is stored, one JSON file a day."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from . import prompt
from .feeds import PAYWALLED, UNLOCKED, Article

# Briefs saved before 0.3.0 had only the FT, and no access: they keep showing "FT".
OLD_SOURCE = "FT"


def label(source: str, access: str, via: str = "") -> str:
    """What the page shows beside an item: "BBC", "FT Edit", "FT · paywalled"."""
    if access == UNLOCKED:
        return via or source
    if access == PAYWALLED:
        return f"{source} · paywalled"
    return source


@dataclass
class Also:
    """Another outlet's (or the same one's) report of a story's event."""

    url: str
    source: str = OLD_SOURCE
    access: str = ""
    via: str = ""

    @property
    def label(self) -> str:
        return label(self.source, self.access, self.via)


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
    also: list[Also] = field(default_factory=list)  # other reports of the same event
    source: str = OLD_SOURCE
    access: str = ""  # free, unlocked or paywalled; "" in briefs from before 0.3.0
    via: str = ""

    @property
    def label(self) -> str:
        return label(self.source, self.access, self.via)


@dataclass
class Line:
    id: str
    url: str
    text: str
    published: str
    source: str = OLD_SOURCE
    access: str = ""
    via: str = ""

    @property
    def label(self) -> str:
        return label(self.source, self.access, self.via)


@dataclass
class Read:
    id: str
    url: str
    headline: str
    note: str
    published: str
    source: str = OLD_SOURCE
    access: str = ""
    via: str = ""

    @property
    def label(self) -> str:
        return label(self.source, self.access, self.via)


def _story(d: dict) -> Story:
    also = [Also(url=a) if isinstance(a, str) else Also(**a) for a in d.get("also", [])]
    return Story(**{k: v for k, v in d.items() if k != "also"}, also=also)


def _origin(a: Article) -> dict:
    return {"source": a.source, "access": a.access, "via": a.via}


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
            stories=[_story(s) for s in d.get("stories", [])],
            lines=[Line(**x) for x in d.get("lines", [])],
            reads=[Read(**r) for r in d.get("reads", [])],
        )


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def from_model(data: dict, candidates: list[Article]) -> tuple[list[Story], list[Line], list[Read]]:
    """Checks a model's answer against the articles it was given and keeps only what holds up.

    Unknown ids, repeats and empty text are dropped, weights are kept in 2-5 and topics to
    three. A story whose id is paywalled links to a readable item in its `also` instead, when
    there is one. Source and access always come from the items, never from the answer.
    Raises ValueError when nothing usable is left, so the next provider gets a turn.
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
        others = [by_id[x] for x in (s.get("also") or []) if take(x)]
        if not a.readable and (open_ := next((o for o in others if o.readable), None)):
            # The link goes to a version the reader can open; the paywalled one is mentioned.
            others = [a] + [o for o in others if o is not open_]
            a = open_
        also = [Also(o.url, **_origin(o)) for o in others]
        stories.append(Story(a.id, a.url, headline, summary, weight, topics[:3], text(s.get("place")), iso(a.published), also,
                             **_origin(a)))
    if not stories:
        raise ValueError("no usable stories in the answer")
    # Most important first; the model's own order breaks ties.
    stories.sort(key=lambda s: -s.weight)

    lines = [
        Line(a.id, a.url, text(x.get("text")), iso(a.published), **_origin(a))
        for x in data.get("lines") or []
        if isinstance(x, dict) and text(x.get("text")) and (a := take(x.get("id")))
    ]
    reads = [
        Read(a.id, a.url, a.title, text(x.get("note")), iso(a.published), **_origin(a))
        for x in data.get("reads") or []
        if isinstance(x, dict) and (a := take(x.get("id")))
    ][:prompt.MAX_READS]
    return stories, lines, reads


def _kind(v: object) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true or false"
    return {str: "a string", int: "a number", float: "a number", list: "a list", dict: "an object"}.get(type(v), type(v).__name__)


def _fits(v: object, spec: dict) -> bool:
    kind = spec.get("type")
    if kind == "string":
        return isinstance(v, str)
    if kind == "integer":
        return isinstance(v, int) and not isinstance(v, bool) and v in spec.get("enum", [v])
    if kind == "array":
        return isinstance(v, list) and all(_fits(x, spec["items"]) for x in v)
    return True


def _wanted(spec: dict) -> str:
    if "enum" in spec:
        return "one of " + ", ".join(map(str, spec["enum"]))
    if spec.get("type") == "array":
        return "a list of strings"
    return "a string"


def problems(data: object, candidates: list[Article]) -> list[str]:
    """Every way an answer breaks prompt.SCHEMA or the rules in prompt.SYSTEM, one line each; [] when none.

    Stricter than from_model, which quietly drops what doesn't hold up: this is for a writer
    that can fix its answer and send it again (`python -m brief ingest`). An answer with no
    problems loses nothing in from_model.
    """
    if not isinstance(data, dict):
        return [f"the answer must be a JSON object, not {_kind(data)}"]
    out: list[str] = []
    by_id = {a.id: a for a in candidates}
    ids = set(by_id)
    used: dict[str, str] = {}
    sections = prompt.SCHEMA["properties"]
    for key in sorted(data.keys() - sections.keys()):
        out.append(f"unknown top-level key {key!r}: the answer has only stories, lines and reads")
    for key, section in sections.items():
        if key not in data:
            out.append(f"{key!r} is missing: use [] when there are none")
            continue
        items = data[key]
        if not isinstance(items, list):
            out.append(f"{key} must be a list, not {_kind(items)}")
            continue
        spec = section["items"]
        for i, item in enumerate(items):
            at = f"{key}[{i}]"
            if not isinstance(item, dict):
                out.append(f"{at} must be an object, not {_kind(item)}")
                continue
            out += [f"{at} has no {k!r}" for k in spec["required"] if k not in item]
            out += [f"{at} has an unknown key {k!r}" for k in sorted(item.keys() - spec["properties"].keys())]
            for k, prop in spec["properties"].items():
                if k in item and not _fits(item[k], prop):
                    got = item[k] if isinstance(item[k], int) and not isinstance(item[k], bool) else _kind(item[k])
                    out.append(f"{at}.{k} must be {_wanted(prop)}, not {got}")
            for k in ("headline", "summary", "text", "note"):
                if isinstance(item.get(k), str) and not item[k].strip():
                    out.append(f"{at}.{k} is empty")
            topics = item.get("topics")
            if key == "stories" and isinstance(topics, list):
                if not 1 <= len(topics) <= 3:
                    out.append(f"{at}.topics must hold one to three topics, not {len(topics)}")
                if any(isinstance(t, str) and not t.strip() for t in topics):
                    out.append(f"{at}.topics has an empty topic")
            own = by_id.get(item.get("id")) if isinstance(item.get("id"), str) else None
            given = item.get("source")
            if own and isinstance(given, str) and " ".join(given.split()).lower() != own.source.lower():
                out.append(f"{at}.source must be {own.source!r}, the source of its id, not {given!r}")
            if key == "stories" and own and not own.readable and isinstance(item.get("also"), list):
                for j, x in enumerate(item["also"]):
                    if isinstance(x, str) and x in by_id and by_id[x].readable:
                        out.append(f"{at}.id {own.id!r} is paywalled but also[{j}] ({by_id[x].source}, {by_id[x].access}) "
                                   "can be opened: make that one the id and put the paywalled one in also")
                        break
            refs = [("id", item.get("id"))]
            if isinstance(item.get("also"), list):
                refs += [(f"also[{j}]", x) for j, x in enumerate(item["also"])]
            for where, ref in refs:
                if not isinstance(ref, str):
                    continue  # the wrong type is already reported
                if ref not in ids:
                    out.append(f"{at}.{where} {ref!r} is not the id of any item")
                elif ref in used:
                    out.append(f"{at}.{where} {ref!r} is already used at {used[ref]}; each id goes in one place only")
                else:
                    used[ref] = f"{at}.{where}"
    if data.get("stories") == []:
        out.append("stories is empty: a brief needs at least one story")
    if isinstance(data.get("reads"), list) and len(data["reads"]) > prompt.MAX_READS:
        out.append(f"reads holds {len(data['reads'])} items; at most {prompt.MAX_READS}")
    return out


def digest(b: Brief, base_url: str = "") -> dict:
    """The brief as another reader wants it: `python -m brief latest --json`, /api/latest.json."""
    origin = lambda x: {"source": x.source, "access": x.access, "label": x.label}  # noqa: E731
    story = lambda s: {"headline": s.headline, "summary": s.summary, "weight": s.weight, "topics": s.topics,  # noqa: E731
                       "place": s.place, "url": s.url, "published": s.published, **origin(s),
                       "also": [{"url": a.url, **origin(a)} for a in s.also]}
    return {
        "date": b.date,
        "issued": b.issued,
        "page": f"{base_url}/{b.date}" if base_url else "",
        "writer": b.writer,
        "by_model": bool(b.writer),
        "window_start": b.window_start,
        "window_end": b.window_end,
        "candidates": b.candidates,
        "lead": story(b.stories[0]) if b.stories else None,
        "top_headlines": [s.headline for s in b.stories[:3]],
        "stories": [story(s) for s in b.stories],
        "lines": [{"text": x.text, "url": x.url, "published": x.published, **origin(x)} for x in b.lines],
        "reads": [{"headline": r.headline, "note": r.note, "url": r.url, "published": r.published, **origin(r)} for r in b.reads],
    }


def without_model(candidates: list[Article]) -> list[Story]:
    """When no model answers: every item as its outlet wrote it, newest first, with no weights."""
    return [
        Story(a.id, a.url, a.title, a.standfirst, 0, [], "", iso(a.published), [], **_origin(a))
        for a in sorted(candidates, key=lambda a: a.published, reverse=True)
    ]


def related(stories: list[Story]) -> list[list[int]]:
    """For each story, the indexes of the other stories that share a topic with it."""
    keys = [{t.lower() for t in s.topics} for s in stories]
    return [[j for j in range(len(stories)) if j != i and keys[i] & keys[j]] for i in range(len(stories))]
