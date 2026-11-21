"""Reading the FT's public RSS feeds: headline, standfirst, link and time for each article.

Nothing here logs in to the FT. The feeds are public; the full articles are not read.
"""

from __future__ import annotations

import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Callable, Iterable

log = logging.getLogger(__name__)

FEED_URL = "https://www.ft.com/{name}?format=rss"
USER_AGENT = "news-brief/0.1 (personal RSS reader)"
_UUID = re.compile(r"/content/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")
_TAG = re.compile(r"<[^>]+>")


@dataclass
class Article:
    id: str
    url: str
    title: str
    standfirst: str
    published: datetime  # aware, UTC
    sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """As `fetch` prints it and pending.json keeps it."""
        return {"id": self.id, "headline": self.title, "standfirst": self.standfirst, "sections": list(self.sections),
                "url": self.url, "published": self.published.isoformat(timespec="seconds")}

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
        return cls(d["id"], d["url"], d["headline"], d["standfirst"], datetime.fromisoformat(d["published"]), list(d["sections"]))


def _clean(text: str | None) -> str:
    return " ".join(unescape(_TAG.sub(" ", text or "")).split())


def _text(item: ET.Element, tag: str) -> str:
    """All the text in a child, including any markup a feed left unescaped."""
    el = item.find(tag)
    return "".join(el.itertext()) if el is not None else ""


def article_id(link: str) -> tuple[str, str]:
    """The FT's content id and a clean link (no tracking query). Other links keep their path."""
    match = _UUID.search(link)
    if match:
        uid = match.group(1)
        return uid, f"https://www.ft.com/content/{uid}"
    bare = link.split("?", 1)[0]
    return bare, bare


def parse_feed(xml: bytes, section: str) -> list[Article]:
    root = ET.fromstring(xml)
    out: list[Article] = []
    for item in root.iter("item"):
        link = _text(item, "link").strip()
        title = _clean(_text(item, "title"))
        date = _text(item, "pubDate")
        if not (link and title and date):
            continue
        try:
            published = parsedate_to_datetime(date).astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        uid, url = article_id(link)
        out.append(Article(uid, url, title, _clean(_text(item, "description")), published, [section]))
    return out


def merge(articles: Iterable[Article]) -> list[Article]:
    """One article per id; an article in several feeds keeps every section it was in."""
    seen: dict[str, Article] = {}
    for a in articles:
        if a.id in seen:
            for s in a.sections:
                if s not in seen[a.id].sections:
                    seen[a.id].sections.append(s)
        else:
            seen[a.id] = Article(a.id, a.url, a.title, a.standfirst, a.published, list(a.sections))
    return sorted(seen.values(), key=lambda a: a.published, reverse=True)


def _download(url: str, timeout: float = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
        return resp.read()


def fetch(sections: Iterable[str], download: Callable[[str], bytes] = _download) -> tuple[list[Article], list[str]]:
    """Every feed's articles, merged, and a line for each feed that failed."""
    articles: list[Article] = []
    errors: list[str] = []
    for name in sections:
        try:
            articles += parse_feed(download(FEED_URL.format(name=name)), name)
        except Exception as exc:  # one feed failing must not stop the others
            log.warning("feed %s failed: %s", name, exc)
            errors.append(f"{name}: {exc}")
    return merge(articles), errors


def in_window(articles: Iterable[Article], start: datetime, end: datetime) -> list[Article]:
    return [a for a in articles if start < a.published <= end]
