"""The brief as a page. Editorial: one serif, a letterspaced nameplate, a hairline index.

Every size, the fonts, the accent's hue, the spacing and the motion come from custom
properties on :root, so the tweaks bar (BRIEF_TWEAKS=1) can turn them without a rebuild.
"""

from __future__ import annotations

from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo

from .model import Brief, Story, related

FONTS_URL = "https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400&display=swap"
TWEAK_FONTS_URL = (
    "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400"
    "&family=Libre+Caslon+Text:ital,wght@0,400;0,700;1,400&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400"
    "&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,400&display=swap"
)

CSS = """
/* Layout: one centred reading column, 720px; the nameplate, the lead, then a hairline index. */
:root {
  --font-display: "EB Garamond", Garamond, "Times New Roman", serif;
  --font-body: "EB Garamond", Garamond, "Times New Roman", serif;
  --font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  --scale: 1; --density: 1; --motion: 1; --weight-head: 500; --accent-h: 183;
  --bg: #ffffff; --ink: #1b1d1e; --ink-2: #3b4447; --muted: #5d6a6e; --line: #d5dbdc; --empty: #c9d1d3;
  --accent: hsl(var(--accent-h) 42% 32%); --flash: hsl(var(--accent-h) 30% 92%);
  --s-lead: calc(54px * var(--scale)); --s-head: calc(25px * var(--scale)); --s-body: calc(18px * var(--scale));
  --s-meta: calc(15px * var(--scale)); --s-plate: calc(34px * var(--scale));
  --row: calc(22px * var(--density)); --section: calc(56px * var(--density)); --num-col: 56px;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #121516; --ink: #e4e8e9; --ink-2: #c0c8ca; --muted: #8c989b; --line: #283033; --empty: #3a4447;
    --accent: hsl(var(--accent-h) 35% 62%); --flash: hsl(var(--accent-h) 20% 18%); color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #121516; --ink: #e4e8e9; --ink-2: #c0c8ca; --muted: #8c989b; --line: #283033; --empty: #3a4447;
  --accent: hsl(var(--accent-h) 35% 62%); --flash: hsl(var(--accent-h) 20% 18%); color-scheme: dark;
}
@media (max-width: 560px) {
  :root { --s-lead: calc(40px * var(--scale)); --s-head: calc(23px * var(--scale)); --s-plate: calc(22px * var(--scale)); --num-col: 38px; }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--font-body); font-size: var(--s-body); line-height: 1.5;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
a { color: inherit; }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.sheet { max-width: 720px; margin: 0 auto; padding-block: calc(64px * var(--density)) calc(72px * var(--density)); }

.plate { text-align: center; display: grid; gap: 10px; margin-bottom: var(--section); }
.plate .k { font-family: var(--font-display); font-size: 13px; letter-spacing: 0.5em; text-transform: uppercase; color: var(--muted); padding-left: 0.5em; }
.plate .n { font-family: var(--font-display); font-weight: 400; margin: 0; font-size: var(--s-plate); letter-spacing: 0.62em; text-transform: uppercase; padding-left: 0.62em; line-height: 1.2; }
.plate .by { font-style: italic; font-size: 16px; color: var(--muted); }
.key { display: inline-flex; gap: 8px; align-items: center; justify-content: center; font-style: italic; font-size: 14px; color: var(--muted); margin-top: 6px; }
@media (max-width: 560px) { .plate .n { letter-spacing: 0.4em; padding-left: 0.4em; } }

.meter { display: inline-flex; gap: 3px; align-items: flex-end; vertical-align: -1px; }
.meter i { width: 3px; height: 12px; background: var(--empty); display: block; }
.meter i.on { background: var(--ink); }
.meter.lg { gap: 4px; }
.meter.lg i { width: 4px; height: 16px; }

.notice { border-top: 1px solid var(--ink); border-bottom: 1px solid var(--line); padding-block: 14px; margin-bottom: var(--section); font-size: var(--s-meta); color: var(--ink-2); }
.notice p { margin: 0; }
.notice details { margin-top: 6px; color: var(--muted); }
.notice summary { cursor: pointer; font-style: italic; }
.notice ul { margin: 6px 0 0; padding-left: 18px; }

.lead { scroll-margin-top: 24px; }
.lead .top { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; margin-bottom: 12px; }
.lead .meta { font-style: italic; color: var(--accent); font-size: 16px; }
.lead h2 { font-family: var(--font-display); font-weight: 400; font-size: var(--s-lead); line-height: 1.08; letter-spacing: -0.01em; margin: 0 0 18px; text-wrap: balance; }
.lead p { font-size: calc(var(--s-body) + 2px); line-height: 1.55; margin: 0; max-width: 60ch; }
h2 a, h3 a { text-decoration: none; }
h2 a:hover, h3 a:hover { text-decoration: underline; text-underline-offset: 3px; text-decoration-thickness: 1px; }

.rel { margin-top: 10px; font-size: var(--s-meta); color: var(--muted); display: flex; flex-wrap: wrap; gap: 2px 12px; align-items: baseline; }
.topics { font-size: calc(var(--s-meta) - 3px); letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-2); }
.topics span + span::before { content: " · "; color: var(--muted); letter-spacing: 0; }
.see, .when { font-style: italic; }
.see a { color: var(--accent); text-decoration: none; }
.see a:hover { text-decoration: underline; }

.idx { margin-top: var(--section); border-top: 1px solid var(--ink); }
.item { display: grid; grid-template-columns: var(--num-col) minmax(0, 1fr); gap: 0 16px; padding-block: var(--row); border-bottom: 1px solid var(--line);
  scroll-margin-top: 24px; transition: background-color calc(900ms * var(--motion)) ease-out; }
.item .no { font-style: italic; font-size: 15px; color: var(--muted); padding-top: 4px; display: grid; gap: 8px; align-content: start; }
.item h3 { font-family: var(--font-display); font-weight: var(--weight-head); font-size: var(--s-head); line-height: 1.25; margin: 0 0 6px; text-wrap: balance; }
.item p { margin: 0; font-size: var(--s-body); line-height: 1.5; color: var(--ink-2); }
.item:target, .lead:target { background-color: var(--flash); }
@media (max-width: 560px) { .item { gap: 0 10px; } }

.sub { margin-top: var(--section); display: grid; gap: 8px; }
.sub h2 { font-family: var(--font-display); font-style: italic; font-weight: 400; font-size: 18px; color: var(--muted); margin: 0 0 4px; }
.sub ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; font-size: var(--s-body); line-height: 1.45; }
.sub a { text-decoration-color: var(--line); text-underline-offset: 3px; }
.sub .w { color: var(--muted); }
.sub .t { font-style: italic; color: var(--muted); font-size: var(--s-meta); white-space: nowrap; }
.empty { font-style: italic; color: var(--muted); text-align: center; }

.foot { margin-top: var(--section); text-align: center; font-style: italic; font-size: 15px; color: var(--muted); display: grid; gap: 10px; }
.foot p { margin: 0; }
.foot nav { display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; font-style: normal; }
.foot nav a { color: var(--accent); text-decoration: none; }
.foot nav a:hover { text-decoration: underline; }

.archive ol { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--ink); }
.archive li a { display: grid; grid-template-columns: 9em minmax(0, 1fr); gap: 4px 16px; padding-block: 14px; border-bottom: 1px solid var(--line); text-decoration: none; }
.archive .d { font-style: italic; color: var(--muted); }
.archive li a:hover .h { text-decoration: underline; }
@media (max-width: 560px) { .archive li a { grid-template-columns: minmax(0, 1fr); } }

@media (prefers-reduced-motion: reduce) { * { transition: none !important; scroll-behavior: auto !important; } }
"""

# The tweaks bar: development only (BRIEF_TWEAKS=1). Each control writes one custom property.
TWEAKS = """
<style>
.tw { position: fixed; z-index: 10; right: max(12px, env(safe-area-inset-right, 0px)); bottom: max(12px, env(safe-area-inset-bottom, 0px));
  width: min(340px, calc(100vw - 24px)); font: 13px/1.4 var(--font-ui); color: var(--ink); background: var(--bg);
  border: 1px solid var(--line); box-shadow: 0 6px 24px hsl(var(--accent-h) 20% 10% / 0.16); }
.tw summary { cursor: pointer; padding: 10px 12px; font-weight: 600; list-style: none; display: flex; justify-content: space-between; }
.tw summary::after { content: "Show"; font-weight: 400; color: var(--muted); }
.tw[open] summary::after { content: "Hide"; }
.tw .body { padding: 0 12px 12px; display: grid; gap: 10px; max-height: 70vh; overflow: auto; }
.tw label { display: grid; grid-template-columns: 7.5em minmax(0, 1fr) 3.2em; gap: 8px; align-items: center; }
.tw output { text-align: right; font-variant-numeric: tabular-nums; color: var(--muted); }
.tw select, .tw input[type=range] { width: 100%; min-height: 28px; }
.tw .row { display: flex; gap: 8px; }
.tw button { font: inherit; padding: 6px 10px; border: 1px solid var(--line); background: var(--bg); color: var(--ink); cursor: pointer; }
.tw button:hover { border-color: var(--ink); }
.tw textarea { width: 100%; height: 110px; font: 12px/1.4 ui-monospace, Menlo, monospace; color: var(--ink); background: var(--bg); border: 1px solid var(--line); }
</style>
<details class="tw" id="tw" open>
  <summary>Tweaks</summary>
  <div class="body">
    <label>Display font <select id="tw-display" data-prop="--font-display"></select><span></span></label>
    <label>Body font <select id="tw-body" data-prop="--font-body"></select><span></span></label>
    <label>Type scale <input id="tw-scale" type="range" min="0.8" max="1.3" step="0.02" data-prop="--scale"><output></output></label>
    <label>Headline weight <input id="tw-weight" type="range" min="400" max="600" step="100" data-prop="--weight-head"><output></output></label>
    <label>Accent hue <input id="tw-hue" type="range" min="0" max="359" step="1" data-prop="--accent-h"><output></output></label>
    <label>Density <input id="tw-density" type="range" min="0.6" max="1.4" step="0.05" data-prop="--density"><output></output></label>
    <label>Motion <input id="tw-motion" type="range" min="0" max="2" step="0.25" data-prop="--motion"><output></output></label>
    <div class="row"><button type="button" id="tw-copy">Show values</button><button type="button" id="tw-reset">Reset</button></div>
    <textarea id="tw-out" readonly hidden aria-label="Current values as CSS"></textarea>
  </div>
</details>
<script>
(() => {
  const serif = ', Garamond, "Times New Roman", serif';
  const FONTS = ["EB Garamond", "Cormorant Garamond", "Libre Caslon Text", "Newsreader", "Source Serif 4", "Fraunces"];
  const root = document.documentElement, KEY = "brief-tweaks";
  const controls = [...document.querySelectorAll(".tw [data-prop]")];
  const base = Object.fromEntries(controls.map(c => [c.dataset.prop, getComputedStyle(root).getPropertyValue(c.dataset.prop).trim()]));
  for (const sel of document.querySelectorAll(".tw select")) for (const f of FONTS) sel.add(new Option(f, '"' + f + '"' + serif));
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) {}
  const show = c => { const o = c.parentElement.querySelector("output"); if (o) o.value = c.value; };
  const apply = (c, v) => { root.style.setProperty(c.dataset.prop, v); c.value = v; show(c); };
  for (const c of controls) {
    let v = saved[c.dataset.prop] || base[c.dataset.prop];
    if (c.tagName === "SELECT" && ![...c.options].some(o => o.value === v)) v = c.options[0].value;
    apply(c, v);
    c.addEventListener("input", () => {
      apply(c, c.value);
      saved[c.dataset.prop] = c.value;
      try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (e) {}
    });
  }
  document.getElementById("tw-reset").addEventListener("click", () => {
    saved = {};
    try { localStorage.removeItem(KEY); } catch (e) {}
    for (const c of controls) { root.style.removeProperty(c.dataset.prop); apply(c, base[c.dataset.prop] || c.value); }
  });
  document.getElementById("tw-copy").addEventListener("click", () => {
    const out = document.getElementById("tw-out");
    out.value = ":root {\\n" + controls.map(c => "  " + c.dataset.prop + ": " + c.value + ";").join("\\n") + "\\n}";
    out.hidden = false; out.select();
  });
})();
</script>
"""


def e(text: object) -> str:
    return escape(str(text), quote=True)


def _local(iso: str, tz: ZoneInfo) -> datetime:
    return datetime.fromisoformat(iso).astimezone(tz)


def _when(iso: str, tz: ZoneInfo) -> str:
    return _local(iso, tz).strftime("%a %H:%M")


def _long_date(d: date) -> str:
    return f"{d.day} {d.strftime('%B')}"


def meter(weight: int, large: bool = False) -> str:
    if not weight:
        return ""
    bars = "".join(f'<i class="{"on" if i <= weight else ""}"></i>' for i in range(1, 6))
    return f'<span class="meter{" lg" if large else ""}" role="img" aria-label="Weight {weight} of 5">{bars}</span>'


def _short(s: Story) -> str:
    """A few words that name a story in an "Also here" link."""
    if s.place:
        return s.place
    words = s.headline.split()
    return " ".join(words[:4]) + ("…" if len(words) > 4 else "")


def _rel(i: int, stories: list[Story], links: list[list[int]]) -> str:
    s = stories[i]
    parts = []
    if s.topics:
        parts.append('<span class="topics">' + "".join(f"<span>{e(t)}</span>" for t in s.topics) + "</span>")
    if links[i]:
        refs = ", ".join(
            f'<a href="#s{j + 1}" title="{e(stories[j].headline)}">#{j + 1:02d} {e(_short(stories[j]))}</a>' for j in links[i]
        )
        parts.append(f'<span class="see">Also here: {refs}</span>')
    if s.also:
        more = ", ".join(f'<a href="{e(u)}" target="_blank" rel="noopener">{n}</a>' for n, u in enumerate(s.also, 1))
        parts.append(f'<span class="see">More FT reports: {more}</span>')
    return f'<div class="rel">{"".join(parts)}</div>' if parts else ""


def _minutes(b: Brief) -> int:
    words = sum(len(s.headline.split()) + len(s.summary.split()) for s in b.stories)
    words += sum(len(x.text.split()) for x in b.lines) + sum(len(r.headline.split()) + len(r.note.split()) for r in b.reads)
    return max(1, round(words / 230))


def _page(title: str, body: str, tweaks: bool) -> str:
    fonts = f'<link rel="stylesheet" href="{FONTS_URL}">' + (f'<link rel="stylesheet" href="{TWEAK_FONTS_URL}">' if tweaks else "")
    return (
        '<!doctype html>\n<html lang="en-GB">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        f"<title>{e(title)}</title>\n"
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        f"{fonts}\n<style>{CSS}</style>\n</head>\n<body>\n{body}\n{TWEAKS if tweaks else ''}\n</body>\n</html>\n"
    )


def brief_page(b: Brief, tz: ZoneInfo, prev_date: str | None = None, next_date: str | None = None, tweaks: bool = False) -> str:
    day = date.fromisoformat(b.date)
    weekend = day.weekday() >= 5
    stories, links = b.stories, related(b.stories)
    weighed = any(s.weight for s in stories)

    plate = (
        f'<header class="plate"><div class="k">{e(day.strftime("%A"))}</div><h1 class="n">Morning Brief</h1>'
        f'<div class="by">from the Financial Times, {e(_long_date(day))}</div>'
        + (f'<div class="key">{meter(3)} <span>weight, one to five</span></div>' if weighed else "")
        + "</header>"
    )

    notice = ""
    if not b.writer and stories:
        items = "".join(f"<li>{e(f)}</li>" for f in b.failures)
        notice = (
            '<section class="notice"><p>No model could write this brief, so these are the FT’s own headlines and '
            "standfirsts, newest first, with no weights or topics.</p>"
            f"<details><summary>What failed</summary><ul>{items}</ul></details></section>"
        )

    body = ""
    if stories:
        lead = stories[0]
        meta = ", ".join(x for x in (lead.topics[0] if lead.topics else "", lead.place) if x)
        meta = f"{e(meta)} · " if meta else ""
        body += (
            f'<article class="lead" id="s1"><div class="top">{meter(lead.weight, True)}'
            f'<span class="meta">{meta}<span class="when">{e(_when(lead.published, tz))}</span></span></div>'
            f'<h2><a href="{e(lead.url)}" target="_blank" rel="noopener">{e(lead.headline)}</a></h2>'
            f"<p>{e(lead.summary)}</p>{_rel(0, stories, links)}</article>"
        )
        rows = []
        for i, s in enumerate(stories[1:], 1):
            where = " · ".join(e(x) for x in (s.place, _when(s.published, tz)) if x)
            rows.append(
                f'<article class="item" id="s{i + 1}"><div class="no"><span>#{i + 1:02d}</span>{meter(s.weight)}</div>'
                f'<div><h3><a href="{e(s.url)}" target="_blank" rel="noopener">{e(s.headline)}</a></h3>'
                + (f"<p>{e(s.summary)}</p>" if s.summary else "")
                + f'<div class="rel"><span class="when">{where}</span></div>{_rel(i, stories, links)}</div></article>'
            )
        if rows:
            body += f'<div class="idx">{"".join(rows)}</div>'
    else:
        body += '<p class="empty">Nothing new from the FT since the last brief.</p>'

    if b.lines:
        lis = "".join(
            f'<li><a href="{e(x.url)}" target="_blank" rel="noopener">{e(x.text)}</a> <span class="t">{e(_when(x.published, tz))}</span></li>'
            for x in b.lines
        )
        body += f'<section class="sub"><h2>Also</h2><ul>{lis}</ul></section>'
    if b.reads:
        lis = "".join(
            f'<li><a href="{e(r.url)}" target="_blank" rel="noopener">{e(r.headline)}</a> <span class="w">{e(r.note)}</span></li>'
            for r in b.reads
        )
        body += f'<section class="sub"><h2>{"For the weekend" if weekend else "For later"}</h2><ul>{lis}</ul></section>'

    start, end = _local(b.window_start, tz), _local(b.window_end, tz)
    count = f"{len(stories)} {'story' if len(stories) == 1 else 'stories'}"
    by = f"Written by {e(b.writer)}." if b.writer else "Not written by a model."
    nav = []
    if prev_date:
        nav.append(f'<a href="/{e(prev_date)}">‹ {e(date.fromisoformat(prev_date).strftime("%A %d %b"))}</a>')
    nav.append('<a href="/archive">All briefs</a>')
    if next_date:
        nav.append(f'<a href="/{e(next_date)}">{e(date.fromisoformat(next_date).strftime("%A %d %b"))} ›</a>')
    foot = (
        f'<footer class="foot"><p>About {_minutes(b)} minute{"s" if _minutes(b) != 1 else ""}. {count} from {b.candidates} FT items, '
        f'{e(start.strftime("%a %H:%M"))} to {e(end.strftime("%a %H:%M"))} ({e(tz.key)}). {by}</p>'
        f'<nav>{"".join(nav)}</nav></footer>'
    )
    return _page(f"Morning Brief, {day.strftime('%a %d %b')}", f'<main class="sheet">{plate}{notice}{body}{foot}</main>', tweaks)


def archive_page(entries: list[tuple[str, str, int]], tweaks: bool = False) -> str:
    """entries: (date, lead headline, story count), newest first."""
    lis = "".join(
        f'<li><a href="/{e(d)}"><span class="d">{e(date.fromisoformat(d).strftime("%a %d %b %Y"))}</span>'
        f'<span><span class="h">{e(h)}</span> <span class="d">· {n} stories</span></span></a></li>'
        for d, h, n in entries
    )
    body = (
        '<main class="sheet archive"><header class="plate"><div class="k">All</div><h1 class="n">Briefs</h1></header>'
        + (f"<ol>{lis}</ol>" if lis else '<p class="empty">No briefs yet. The first one arrives at the next run.</p>')
        + '<footer class="foot"><nav><a href="/">Latest brief</a></nav></footer></main>'
    )
    return _page("Morning Brief archive", body, tweaks)
