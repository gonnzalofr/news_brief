"""One morning's run: read the feeds, have a model write the brief, save it, push it."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

from . import feeds, llm, notify, prompt
from .config import Config
from .model import Brief, from_model, iso, without_model
from .store import Store

log = logging.getLogger(__name__)


class NoFeeds(RuntimeError):
    """Every feed failed: there is nothing to write a brief from."""


def window(store: Store, cfg: Config, now: datetime) -> tuple[datetime, datetime]:
    """From where the previous day's brief stopped to now; 24 hours for the first one, at most 72."""
    today = now.astimezone(cfg.tz).date().isoformat()
    earliest = now - timedelta(hours=cfg.max_window_hours)
    prev = store.latest_before(today)
    start = datetime.fromisoformat(prev.window_end) if prev else now - timedelta(hours=24)
    return max(start, earliest), now


def run(
    cfg: Config,
    store: Store,
    now: datetime | None = None,
    push: bool = True,
    fetch: Callable = feeds.fetch,
    chain: list | None = None,
    send: Callable = notify.send,
) -> Brief:
    now = (now or datetime.now(cfg.tz)).astimezone(cfg.tz)
    store.set_state(last_attempt=iso(now))
    start, end = window(store, cfg, now)

    articles, feed_errors = fetch(cfg.feeds)
    if not articles:
        msg = "Every FT feed failed: " + "; ".join(feed_errors)[:500]
        store.set_state(last_error=msg)
        if push:
            send(cfg.ntfy_url, cfg.ntfy_token, "Morning brief failed", msg, priority=4, tags=["warning"])
        raise NoFeeds(msg)
    candidates = feeds.in_window(articles, start, end)
    log.info("%d articles from %d feeds, %d in the window", len(articles), len(cfg.feeds), len(candidates))

    stories, lines, reads, writer, failures = [], [], [], "", []
    if candidates:
        outcome = llm.write(
            chain if chain is not None else llm.providers(cfg),
            prompt.SYSTEM,
            prompt.user_message(candidates, cfg.tz, start, end),
            prompt.SCHEMA,
            check=lambda data: from_model(data, candidates),
        )
        failures = outcome.failures
        if outcome.value:
            stories, lines, reads = outcome.value
            writer = outcome.writer
        else:
            stories = without_model(candidates)

    brief = Brief(
        date=now.date().isoformat(),
        issued=iso(now),
        window_start=iso(start),
        window_end=iso(end),
        candidates=len(candidates),
        stories=stories,
        lines=lines,
        reads=reads,
        writer=writer,
        failures=failures + [f"feed {x}" for x in feed_errors],
    )
    store.save(brief)
    store.set_state(last_success=iso(now), last_error="", last_writer=writer)

    if push:
        _push(cfg, brief, send)
    return brief


def _push(cfg: Config, brief: Brief, send: Callable) -> None:
    day = datetime.fromisoformat(brief.issued)
    title = f"Morning brief · {day.strftime('%a %d %b')}"
    if not brief.stories:
        lines = ["Nothing new from the FT since the last brief."]
    else:
        lines = [f"• {s.headline}" for s in brief.stories[:3]]
        if len(brief.stories) > 3:
            lines.append(f"and {len(brief.stories) - 3} more")
    if brief.stories and not brief.writer:
        lines.append("No model could write it today: these are the FT's own headlines.")
    click = f"{cfg.brief_url}/{brief.date}" if cfg.brief_url else ""
    send(cfg.ntfy_url, cfg.ntfy_token, title, "\n".join(lines), click=click,
         priority=3 if brief.writer or not brief.stories else 4, tags=["newspaper"])
