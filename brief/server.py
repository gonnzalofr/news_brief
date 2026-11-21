"""The pages: / (latest), /<YYYY-MM-DD>, /archive, and /healthz and /readyz for the homelab."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import render
from .config import Config
from .store import Store

log = logging.getLogger(__name__)

CSP = (
    "default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
    "script-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


def make_handler(cfg: Config, store: Store) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "news-brief"
        sys_version = ""

        def log_message(self, fmt: str, *args: object) -> None:
            log.debug("%s %s", self.address_string(), fmt % args)

        def _send(self, status: int, body: str, ctype: str = "text/html; charset=utf-8") -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if ctype.startswith("text/html"):
                self.send_header("Content-Security-Policy", CSP)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _brief(self, day: str) -> None:
            brief = store.load(day)
            if brief is None:
                self._send(HTTPStatus.NOT_FOUND, render.archive_page(self._entries(), cfg.tweaks))
                return
            prev, nxt = store.neighbours(day)
            self._send(HTTPStatus.OK, render.brief_page(brief, cfg.tz, prev, nxt, cfg.tweaks))

        def _entries(self) -> list[tuple[str, str, int]]:
            out = []
            for d in reversed(store.dates()):
                b = store.load(d)
                if b:
                    out.append((d, b.stories[0].headline if b.stories else "Nothing new", len(b.stories)))
            return out

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET()

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path == "/healthz":
                self._send(HTTPStatus.OK, json.dumps({"ok": True} | store.state()), "application/json")
            elif path == "/readyz":
                # Not ready when the last good brief is more than a day and a bit old.
                last = store.state().get("last_success")
                fresh = bool(last) and datetime.now(cfg.tz) - datetime.fromisoformat(last) < timedelta(hours=26)
                self._send(HTTPStatus.OK if fresh else HTTPStatus.SERVICE_UNAVAILABLE,
                           json.dumps({"ready": fresh, "last_success": last}), "application/json")
            elif path == "/":
                dates = store.dates()
                if dates:
                    self._brief(dates[-1])
                else:
                    self._send(HTTPStatus.OK, render.archive_page([], cfg.tweaks))
            elif path == "/archive":
                self._send(HTTPStatus.OK, render.archive_page(self._entries(), cfg.tweaks))
            else:
                self._brief(path.lstrip("/"))

    return Handler


def serve(cfg: Config, store: Store) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), make_handler(cfg, store))
    httpd.daemon_threads = True
    return httpd
