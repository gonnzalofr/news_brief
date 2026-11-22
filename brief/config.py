"""Settings, all from the environment. `.env.example` lists every one with a comment."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

# The outlets and their feeds. SOURCES_FILE points at another copy to change them without a rebuild.
DEFAULT_SOURCES = Path(__file__).resolve().parent / "sources.toml"
ACCESS = ("free", "paywalled")


@dataclass(frozen=True)
class Source:
    """One outlet, as sources.toml has it."""

    name: str  # shown next to each item: "BBC", "FT"
    feeds: tuple[tuple[str, str], ...]  # (section, url)
    access: str = "free"  # "free", or "paywalled": only items in `unlocked` open in full
    unlocked: str = ""  # a feed whose items the reader's subscription opens (FT Edit)
    unlocked_label: str = ""  # how those items are shown: "FT Edit"


@dataclass(frozen=True)
class Config:
    tz: ZoneInfo
    run_at: time
    data_dir: Path
    sources: tuple[Source, ...]
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
    # "internal": `serve` writes the brief itself at BRIEF_TIME. "external": an agent does it
    # with `fetch` and `ingest`, and `serve` only serves the pages.
    mode: str = "internal"
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


def _https(url: object, where: str) -> str:
    if not isinstance(url, str) or urlsplit(url.strip()).scheme not in {"https", "http"}:
        raise ConfigError(f"{where} must be a feed URL, got {url!r}")
    return url.strip()


def load_sources(path: Path) -> tuple[Source, ...]:
    """The outlets in a sources.toml, checked; ConfigError says what is wrong and where."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"can't read the sources in {path}: {exc}") from exc
    out: list[Source] = []
    for i, s in enumerate(data.get("source") or []):
        at = f"{path.name}: source {i + 1}"
        name = " ".join(str(s.get("name") or "").split())
        if not name:
            raise ConfigError(f"{at} has no name")
        at = f"{path.name}: {name}"
        access = s.get("access", "free")
        if access not in ACCESS:
            raise ConfigError(f"{at}: access must be free or paywalled, got {access!r}")
        feeds = s.get("feeds")
        if not isinstance(feeds, dict) or not feeds:
            raise ConfigError(f"{at} has no feeds: add [source.feeds] with section = \"https://...\"")
        unlocked = _https(s["unlocked"], f"{at}: unlocked") if s.get("unlocked") else ""
        if unlocked and access != "paywalled":
            raise ConfigError(f"{at}: unlocked is only for a paywalled source")
        if any(x.name.lower() == name.lower() for x in out):
            raise ConfigError(f"{at} is listed twice")
        out.append(Source(
            name=name,
            feeds=tuple((str(k), _https(v, f"{at}: feed {k}")) for k, v in feeds.items()),
            access=access,
            unlocked=unlocked,
            unlocked_label=" ".join(str(s.get("unlocked_label") or "").split()) or (f"{name}, unlocked" if unlocked else ""),
        ))
    if not out:
        raise ConfigError(f"{path} lists no sources")
    return tuple(out)


def load(env: dict[str, str] | None = None) -> Config:
    env = dict(os.environ if env is None else env)
    get = lambda key, default="": (env.get(key) or default).strip()  # noqa: E731 - an empty value counts as unset

    ntfy_url = get("NTFY_URL")
    if ntfy_url and not urlsplit(ntfy_url).path.strip("/"):
        raise ConfigError("NTFY_URL must name a topic: https://ntfy.sh/<topic>")
    effort = get("ANTHROPIC_EFFORT", "medium")
    if effort not in {"low", "medium", "high", "xhigh", "max"}:
        raise ConfigError(f"ANTHROPIC_EFFORT must be low, medium, high, xhigh or max, got {effort!r}")
    mode = get("BRIEF_MODE", "internal").lower()
    if mode not in {"internal", "external"}:
        raise ConfigError(f"BRIEF_MODE must be internal or external, got {mode!r}")
    try:
        port = int(get("PORT", "4960"))
    except ValueError as exc:
        raise ConfigError("PORT must be a number") from exc

    return Config(
        tz=ZoneInfo(get("TZ", "Europe/Amsterdam")),
        run_at=_time(get("BRIEF_TIME", "07:00")),
        data_dir=Path(get("DATA_DIR", "./data")),
        sources=load_sources(Path(get("SOURCES_FILE")) if get("SOURCES_FILE") else DEFAULT_SOURCES),
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
        mode=mode,
    )
