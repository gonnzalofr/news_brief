from __future__ import annotations

from datetime import datetime, timezone

from brief import config
from brief.feeds import Article

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>World</title>
<item><title>Ministers agree &#8216;a deal&#8217; on grain</title>
<link>https://www.ft.com/content/11111111-1111-1111-1111-111111111111?syn-25a6b1a6=1</link>
<description>The accord covers <b>shipping</b> through the Black Sea</description>
<pubDate>Sat, 21 Nov 2026 18:07:02 GMT</pubDate></item>
<item><title>Central bank holds rates</title>
<link>https://www.ft.com/content/22222222-2222-2222-2222-222222222222</link>
<description>Inflation is still above target</description>
<pubDate>Sat, 21 Nov 2026 05:00:00 GMT</pubDate></item>
<item><title>No date here</title><link>https://www.ft.com/content/33333333-3333-3333-3333-333333333333</link></item>
</channel></rss>"""


def cfg(tmp: str = "/tmp", **env: str) -> config.Config:
    base = {"DATA_DIR": tmp, "TZ": "Europe/Amsterdam", "BRIEF_TIME": "07:00"}
    return config.load(base | env)


def art(n: int, title: str, hour: int, day: int = 21, standfirst: str = "") -> Article:
    uid = f"{n:08d}-0000-0000-0000-000000000000"
    return Article(uid, f"https://www.ft.com/content/{uid}", title, standfirst or f"About {title.lower()}",
                   datetime(2026, 11, day, hour, 0, tzinfo=timezone.utc), ["world"])
