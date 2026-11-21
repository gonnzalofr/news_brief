"""Settings, all from the environment. `.env.example` lists every one with a comment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

# FT section feeds. Each is https://www.ft.com/<name>?format=rss: headline, standfirst, link, time.
DEFAULT_FEEDS = (
    "world,us,europe,asia-pacific,middle-east-north-africa,africa,americas,world-uk,"
    "global-economy,companies,markets,technology,climate-capital,opinion"
)


@dataclass(frozen=True)
class Config:
    tz: ZoneInfo
    run_at: time
    data_dir: Path
    feeds: tuple[str, ...]
    anthropic_key: str
    anthropic_model: str
    anthropic_effort: str
    gemini_key: str
    gemini_model: str
    openai_key: str
    openai_model: str
    ntfy_url: str
    ntfy_token: str
    brief_url: str
    host: str
    port: int
    tweaks: bool
    # The first brief, or one after a gap, covers at most this many hours.
    max_window_hours: int = 72


class ConfigError(ValueError):
    pass


def _time(value: str) -> time:
    try:
        hh, mm = value.split(":")
        return time(int(hh), int(mm))
    except ValueError as exc:
        raise ConfigError(f"BRIEF_TIME must be HH:MM, got {value!r}") from exc


def load(env: dict[str, str] | None = None) -> Config:
    env = dict(os.environ if env is None else env)
    get = lambda key, default="": (env.get(key) or default).strip()  # noqa: E731 - an empty value counts as unset

    ntfy_url = get("NTFY_URL")
    if ntfy_url and not urlsplit(ntfy_url).path.strip("/"):
        raise ConfigError("NTFY_URL must name a topic: https://ntfy.sh/<topic>")
    effort = get("ANTHROPIC_EFFORT", "medium")
    if effort not in {"low", "medium", "high", "xhigh", "max"}:
        raise ConfigError(f"ANTHROPIC_EFFORT must be low, medium, high, xhigh or max, got {effort!r}")
    try:
        port = int(get("PORT", "4960"))
    except ValueError as exc:
        raise ConfigError("PORT must be a number") from exc

    return Config(
        tz=ZoneInfo(get("TZ", "Europe/Amsterdam")),
        run_at=_time(get("BRIEF_TIME", "07:00")),
        data_dir=Path(get("DATA_DIR", "./data")),
        feeds=tuple(f.strip().strip("/") for f in get("FEEDS", DEFAULT_FEEDS).split(",") if f.strip()),
        anthropic_key=get("ANTHROPIC_API_KEY"),
        anthropic_model=get("ANTHROPIC_MODEL", "claude-opus-5-5"),
        anthropic_effort=effort,
        gemini_key=get("GEMINI_API_KEY"),
        gemini_model=get("GEMINI_MODEL", "gemini-3.7-flash"),
        openai_key=get("OPENAI_API_KEY"),
        openai_model=get("OPENAI_MODEL", "gpt-5.4-mini"),
        ntfy_url=ntfy_url,
        ntfy_token=get("NTFY_TOKEN"),
        brief_url=get("BRIEF_URL").rstrip("/"),
        host=get("HOST", "0.0.0.0"),
        port=port,
        tweaks=get("BRIEF_TWEAKS") in {"1", "true", "yes"},
    )
