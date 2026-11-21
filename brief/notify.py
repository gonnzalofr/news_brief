"""The push to the phone, through ntfy, like the homelab's other services."""

from __future__ import annotations

import json
import logging
import urllib.request
from urllib.parse import urlsplit

log = logging.getLogger(__name__)


def send(ntfy_url: str, token: str, title: str, message: str, click: str = "", priority: int = 3, tags: list[str] | None = None) -> bool:
    """Publishes as JSON, so the title and message may hold any character. False when it failed."""
    if not ntfy_url:
        log.info("no NTFY_URL set; not sending %r", title)
        return False
    parts = urlsplit(ntfy_url)
    body = {"topic": parts.path.strip("/"), "title": title, "message": message, "priority": priority, "tags": tags or []}
    if click:
        body["click"] = click
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{parts.scheme}://{parts.netloc}/", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - the operator's own ntfy server
            return 200 <= resp.status < 300
    except Exception as exc:  # a failed push must never fail the brief
        log.warning("ntfy push failed: %s", exc)
        return False
