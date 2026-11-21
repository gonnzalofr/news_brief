"""Briefs on disk: DATA_DIR/briefs/<YYYY-MM-DD>.json, one a day, state.json for the last run, and
pending.json between `fetch` and `ingest`."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .model import Brief

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _write(path: Path, text: str) -> None:
    """Whole or not at all: a reader never sees half a file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.briefs = self.root / "briefs"
        self.briefs.mkdir(parents=True, exist_ok=True)

    def save(self, brief: Brief) -> None:
        _write(self.briefs / f"{brief.date}.json", json.dumps(brief.to_dict(), ensure_ascii=False, indent=1))

    def dates(self) -> list[str]:
        """Every day with a brief, oldest first."""
        return sorted(p.stem for p in self.briefs.glob("*.json") if _DATE.match(p.stem))

    def load(self, day: str) -> Brief | None:
        if not _DATE.match(day):
            return None
        path = self.briefs / f"{day}.json"
        if not path.exists():
            return None
        return Brief.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def latest(self) -> Brief | None:
        ds = self.dates()
        return self.load(ds[-1]) if ds else None

    def latest_before(self, day: str) -> Brief | None:
        earlier = [d for d in self.dates() if d < day]
        return self.load(earlier[-1]) if earlier else None

    def neighbours(self, day: str) -> tuple[str | None, str | None]:
        ds = self.dates()
        before = [d for d in ds if d < day]
        after = [d for d in ds if d > day]
        return (before[-1] if before else None, after[0] if after else None)

    def state(self) -> dict:
        path = self.root / "state.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def set_state(self, **values: object) -> None:
        state = self.state() | values
        _write(self.root / "state.json", json.dumps(state, ensure_ascii=False, indent=1))

    @property
    def pending_path(self) -> Path:
        return self.root / "pending.json"

    def save_pending(self, pending: dict) -> None:
        _write(self.pending_path, json.dumps(pending, ensure_ascii=False, indent=1))

    def load_pending(self) -> dict | None:
        try:
            return json.loads(self.pending_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    def clear_pending(self) -> None:
        self.pending_path.unlink(missing_ok=True)
