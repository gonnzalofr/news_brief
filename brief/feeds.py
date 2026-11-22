"""Reading the outlets' public feeds (brief/sources.toml): headline, standfirst, link and time.

Nothing here logs in anywhere. The feeds are public; the articles themselves are not read.
A paywalled outlet can name an `unlocked` feed (the FT's FT Edit): its items are marked as
readable, and the outlet's other items as paywalled.
"""

from __future__ import annotations

import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Callable, Iterable
from urllib.parse import urlsplit

from .config import Source

log = logging.getLogger(__name__)

USER_AGENT = "news-brief/0.3 (personal RSS reader)"
_UUID = re.compile(r"/content/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
_TAG = re.compile(r"<[^>]+>")
_ATOM = "{http://www.w3.org/2005/Atom}"
_DC = "{http://purl.org/dc/elements/1.1/}"

# How an item opens: in full for anyone, through the reader's subscription, or not at all.
FREE, UNLOCKED, PAYWALLED = "free", "unlocked", "paywalled"


@dataclass
class Article:
    id: str
    url: str
    title: str
    standfirst: str
    published: datetime  # aware, UTC
    sections: list[str] = field(default_factory=list)
    source: str = "FT"  # the outlet, as sources.toml names it
    access: str = PAYWALLED  # FREE, UNLOCKED or PAYWALLED
    via: str = ""  # what unlocks it, when UNLOCKED: "FT Edit"

    @property
    def readable(self) -> bool:
        return self.access in (FREE, UNLOCKED)

    def to_dict(self) -> dict:
        """As `fetch` prints it and pending.json keeps it."""
        return {"id": self.id, "source": self.source, "access": self.access, "via": self.via, "headline": self.title,
                "standfirst": self.standfirst, "sections": list(self.sections), "url": self.url,
                "published": self.published.isoformat(timespec="seconds")}

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
        return cls(d["id"], d["url"], d["headline"], d["standfirst"], datetime.fromisoformat(d["published"]), list(d["sections"]),
                   d.get("source", "FT"), d.get("access", PAYWALLED), d.get("via", ""))


def _clean(text: str | None) -> str:
    return " ".join(unescape(_TAG.sub(" ", text or "")).split())


def _text(item: ET.Element, *tags: str) -> str:
    """All the text in the first of these children that has some, including any markup a feed left unescaped."""
    for tag in tags:
        el = item.find(tag)
        if el is not None and (text := "".join(el.itertext()).strip()):
            return text
    return ""


def article_id(link: str) -> tuple[str, str]:
    """An id and a clean link (no tracking query or fragment). For the FT, its content id."""
    if urlsplit(link).netloc.endswith("ft.com") and (match := _UUID.search(link)):
        uid = match.group(1)
        return uid, f"https://www.ft.com/content/{uid}"
    bare = link.split("#", 1)[0].split("?", 1)[0]
    return bare, bare


def _date(text: str) -> datetime | None:
    """RFC 822 (RSS) or ISO 8601 (Atom, Dublin Core), as UTC; None when it is neither."""
    if not text:
        return None
    try:
        d = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _atom_link(entry: ET.Element) -> str:
    for el in entry.findall(_ATOM + "link"):
        if el.get("rel", "alternate") == "alternate" and el.get("href"):
            return el.get("href", "")
    return ""


def parse_feed(xml: bytes, section: str, source: str = "FT") -> list[Article]:
    """An RSS 2.0 or Atom feed's items. Ones without a link, headline or time are left out."""
    root = ET.fromstring(xml)
    out: list[Article] = []
    rss = list(root.iter("item"))
    for item in rss or root.iter(_ATOM + "entry"):
        if rss:
            link, title = _text(item, "link"), _clean(_text(item, "title"))
            published = _date(_text(item, "pubDate", _DC + "date"))
            standfirst = _clean(_text(item, "description"))
        else:
            link, title = _atom_link(item), _clean(_text(item, _ATOM + "title"))
            published = _date(_text(item, _ATOM + "published", _ATOM + "updated"))
            standfirst = _clean(_text(item, _ATOM + "summary"))
        if not (link and title and published):
            continue
        uid, url = article_id(link)
        out.append(Article(uid, url, title, standfirst[:600], published, [section], source))
    return out


def merge(articles: Iterable[Article]) -> list[Article]:
    """One article per id; an article in several feeds keeps every section it was in. Newest first."""
    seen: dict[str, Article] = {}
    for a in articles:
        if a.id in seen:
            for s in a.sections:
                if s not in seen[a.id].sections:
                    seen[a.id].sections.append(s)
        else:
            seen[a.id] = Article(a.id, a.url, a.title, a.standfirst, a.published, list(a.sections), a.source, a.access, a.via)
    return sorted(seen.values(), key=lambda a: a.published, reverse=True)


def _download(url: str, timeout: float = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URLs from sources.toml
        return resp.read()


def fetch(sources: Iterable[Source], download: Callable[[str], bytes] = _download) -> tuple[list[Article], list[str]]:
    """Every feed's articles, merged and marked free, unlocked or paywalled, and a line for each feed that failed.

    A paywalled source's items are unlocked when its `unlocked` feed has them. When that feed
    fails, all of them count as paywalled: the brief never says an item opens when it may not.
    """
    sources = list(sources)
    jobs = [(s, section, url) for s in sources for section, url in s.feeds]
    jobs += [(s, s.unlocked_label, s.unlocked) for s in sources if s.unlocked]

    def one(job: tuple[Source, str, str]) -> list[Article] | Exception:
        s, section, url = job
        try:
            return parse_feed(download(url), section, s.name)
        except Exception as exc:  # one feed failing must not stop the others
            return exc

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(one, jobs))

    articles: list[Article] = []
    errors: list[str] = []
    unlocked: set[tuple[str, str]] = set()
    for (s, section, url), got in zip(jobs, results):
        if isinstance(got, Exception):
            log.warning("feed %s %s failed: %s", s.name, section, got)
            errors.append(f"{s.name} {section}: {got}")
            continue
        if s.unlocked and url == s.unlocked:
            unlocked |= {(s.name, a.id) for a in got}
        articles += got
    by_name = {s.name: s for s in sources}
    for a in articles:
        s = by_name[a.source]
        if s.access == FREE:
            a.access, a.via = FREE, ""
        elif (a.source, a.id) in unlocked:
            a.access, a.via = UNLOCKED, s.unlocked_label
        else:
            a.access, a.via = PAYWALLED, ""
    return merge(articles), errors


def in_window(articles: Iterable[Article], start: datetime, end: datetime) -> list[Article]:
    return [a for a in articles if start < a.published <= end]
