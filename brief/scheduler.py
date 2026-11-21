"""Runs the job once a day at BRIEF_TIME, in the configured time zone."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, time, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

# Started late (a restart, a reboot): still write today's brief if it's this soon after the time.
CATCH_UP = timedelta(hours=4)


def next_run(now: datetime, at: time, tz: ZoneInfo) -> datetime:
    """The next local `at` strictly after `now`. Built from the local date, so DST is handled."""
    local = now.astimezone(tz)
    candidate = datetime.combine(local.date(), at, tzinfo=tz)
    if candidate <= local:
        candidate = datetime.combine(local.date() + timedelta(days=1), at, tzinfo=tz)
    return candidate


def due_now(now: datetime, at: time, tz: ZoneInfo, has_today: bool) -> bool:
    """True when today's time has passed, within CATCH_UP, and there is no brief for today yet."""
    local = now.astimezone(tz)
    today_at = datetime.combine(local.date(), at, tzinfo=tz)
    return not has_today and today_at <= local < today_at + CATCH_UP


def loop(at: time, tz: ZoneInfo, job: Callable[[], object], has_today: Callable[[], bool], stop: threading.Event) -> None:
    if due_now(datetime.now(tz), at, tz, has_today()):
        log.info("today's brief is late; writing it now")
        _safe(job)
    while not stop.is_set():
        target = next_run(datetime.now(tz), at, tz)
        log.info("next brief at %s", target.isoformat(timespec="minutes"))
        # Short waits, so a changed clock (suspend, NTP) can't push the run far off.
        while not stop.is_set() and datetime.now(tz) < target:
            stop.wait(min(60.0, max(0.5, (target - datetime.now(tz)).total_seconds())))
        if not stop.is_set():
            _safe(job)


def _safe(job: Callable[[], object]) -> None:
    try:
        job()
    except Exception:  # one bad morning must not stop tomorrow's
        log.exception("the brief failed")
