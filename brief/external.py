"""The brief written by an agent outside this process, instead of a model API.

`fetch` reads the feeds, keeps the items in DATA_DIR/pending.json and hands the agent the
items with the editor's instructions and the schema from prompt.py. `ingest` checks the
agent's answer against exactly those items, with model.py's rules, and publishes it like a
model-written brief: saved, recorded in state.json (so /readyz sees it), pushed.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Callable

from . import feeds, job, notify, prompt
from .config import Config
from .feeds import Article
from .model import Brief, from_model, iso, problems, without_model
from .store import Store

log = logging.getLogger(__name__)

PENDING_VERSION = 1
DEFAULT_WRITER = "an external agent"
_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n(.*)\n```$", re.DOTALL)


class NoPending(RuntimeError):
    """There is no pending.json to check an answer against."""


class Invalid(ValueError):
    """The answer doesn't hold up; `problems` says how, one line each. Nothing was saved."""

    def __init__(self, found: list[str]):
        super().__init__(f"{len(found)} problem{'s' if len(found) != 1 else ''}")
        self.problems = found


def fetch(
    cfg: Config, store: Store, now: datetime | None = None, push: bool = True,
    fetch: Callable | None = None, send: Callable | None = None,
) -> dict:
    """Reads the feeds, saves pending.json, and returns what the agent needs to write the brief.

    Raises job.NoFeeds (pushed, unless push is False) when every feed failed.
    """
    now = (now or datetime.now(cfg.tz)).astimezone(cfg.tz)
    start, end, candidates, feed_errors = job.collect(cfg, store, now, push, fetch or feeds.fetch, send or notify.send)
    day = now.date()
    brief = {
        "date": day.isoformat(),
        "fetched": iso(now),
        "window_start": iso(start),
        "window_end": iso(end),
        "timezone": cfg.tz.key,
        "weekend": day.weekday() >= 5,
        "candidates": len(candidates),
        "feed_errors": feed_errors,
    }
    items = [a.to_dict() for a in candidates]
    store.save_pending({"version": PENDING_VERSION, "brief": brief, "items": items})
    log.info("%d items for %s kept in %s", len(items), brief["date"], store.pending_path)
    how = prompt.AGENT if candidates else (
        "The FT published nothing in this window. Run `python -m brief ingest --fallback` to send "
        "the brief that says so."
    )
    return {
        "brief": brief,
        "instructions": {
            "how": how,
            "context": prompt.window_note(len(candidates), cfg.tz, start, end) + ".",
            "system": prompt.SYSTEM,
            "schema": prompt.SCHEMA,
        },
        "items": items,
        "pending": str(store.pending_path),
    }


def parse(text: str | None) -> object:
    """The agent's JSON. A Markdown code fence around it is allowed."""
    text = (text or "").strip()
    if match := _FENCE.match(text):
        text = match.group(1).strip()
    if not text:
        raise Invalid(["the answer is empty: send one JSON object with stories, lines and reads"])
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise Invalid([f"the answer is not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}"]) from exc


def load_pending(store: Store) -> tuple[dict, list[Article]]:
    pending = store.load_pending()
    if pending is None:
        raise NoPending(f"No pending brief at {store.pending_path}: run `python -m brief fetch` first.")
    if pending.get("version") != PENDING_VERSION:
        raise NoPending(f"{store.pending_path} is from another version of news_brief: run `python -m brief fetch` again.")
    return pending["brief"], [Article.from_dict(d) for d in pending["items"]]


def ingest(
    cfg: Config, store: Store, text: str | None, writer: str = "", day: str = "", fallback: bool = False,
    push: bool = True, now: datetime | None = None, send: Callable | None = None,
) -> tuple[Brief, bool]:
    """Checks the answer against pending.json and publishes the brief; then pending.json goes.

    The brief and whether the push went out. Raises NoPending, or Invalid with every problem
    found, in which case nothing is saved and pending.json stays for the next try. With
    `fallback`, or when the window held no items, `text` is not read: the FT's own headlines go out.
    """
    meta, candidates = load_pending(store)
    now = (now or datetime.now(cfg.tz)).astimezone(cfg.tz)
    failures = [f"feed {x}" for x in meta.get("feed_errors", [])]

    if fallback or not candidates:
        stories, lines, reads, writer = without_model(candidates), [], [], ""
        if candidates:
            failures.insert(0, "the agent sent no brief (ingest --fallback)")
    else:
        data = parse(text)
        found = problems(data, candidates)
        if found:
            raise Invalid(found)
        stories, lines, reads = from_model(data, candidates)
        writer = " ".join(writer.split())[:80] or DEFAULT_WRITER

    brief = Brief(
        date=day or meta["date"],
        issued=iso(now),
        window_start=meta["window_start"],
        window_end=meta["window_end"],
        candidates=len(candidates),
        stories=stories,
        lines=lines,
        reads=reads,
        writer=writer,
        failures=failures,
    )
    pushed = job.publish(cfg, store, brief, push, send or notify.send)
    store.clear_pending()
    log.info("%s: %d stories by %s", brief.date, len(brief.stories), brief.writer or "no model")
    return brief, pushed
