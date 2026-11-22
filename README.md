# news_brief

A morning brief of world news for one reader, from the FT and a handful of free outlets. Every
day at 07:00 it reads their public feeds, has a model pick and summarise every story worth
knowing, keeps the brief as a page, and pushes the top three headlines to the phone through
ntfy. It runs as one Docker image on the homelab, reached over Tailscale.

## What a brief holds

- **Every story that matters**, with no fixed number: a busy night gives a long brief. Each has a
  short summary, a **weight** from two to five strokes (how far beyond today it is likely to
  matter), its **topics** in small capitals, **links to the other stories** in the same brief
  that share a topic, its place, and the time it was published.
- **Also**: smaller news, one line each.
- **For later** (for the weekend on Saturdays and Sundays): analysis and opinion worth reading.
- **Where each item is from**, beside its headline: the outlet (`BBC`, `Guardian`), `FT Edit`
  for an FT piece the reader's FT Edit licence opens, or `FT · paywalled` for one it doesn't.
- When several outlets report the same event it is one story: the headline links to a version
  the reader can open, and *Also reported by* links the others (`FT · paywalled, DW, CNBC (1, 2)`).

Past briefs stay at `/<date>` and are listed at `/archive`.

## Where the news comes from

Public RSS and Atom feeds, listed in [`brief/sources.toml`](brief/sources.toml), the one file to
edit to add, drop or change an outlet (or point `SOURCES_FILE` at your own copy, to change it
without rebuilding the image). A feed item has a headline, a one-line standfirst, a link and a
time; that is all the model sees, and the summaries are built only from it. Nothing here logs in
anywhere or reads the full articles: no keys, no cookies, no scraping.

| Outlet | Feeds | Why |
| --- | --- | --- |
| FT | world, the regions, the economy, companies, markets, technology, climate, opinion; FT Edit | The reader's paper; paywalled except FT Edit |
| BBC | world, business, technology | Broadest free general news in English, careful with facts |
| Guardian | world, Europe, business, economics, AI | No paywall; deep world and Europe desks, a dedicated AI section |
| DW | top stories, Europe, business | The EU and Central and Eastern Europe from Berlin |
| Politico Europe | all | The EU institutions from the inside |
| Al Jazeera | all | The Middle East, Africa and South Asia, with reporters on the ground |
| CNBC | top news, economy, finance | Markets and the US economy as they move |
| Ars Technica | all | Technology and science by specialists, sober about AI |
| TechCrunch | AI | The AI industry day to day |

Reuters and AP have no public feeds any more; France 24, Euronews and NPR were checked and are
in the file, commented out. No outlet gets a quota: the model ranks every item on its news value.

**The FT and FT Edit.** The reader's FT licence is FT Edit: the eight pieces a day the FT's
editors pick open in full, and any other FT article asks to subscribe. The FT publishes that
selection as a public feed, `https://www.ft.com/ft-edit?format=rss` (the stream behind
ft.com/ft-edit; the page itself refuses automated readers). Every FT item in that feed when the
brief is fetched is `unlocked` and shown as **FT Edit**; every other FT item is `paywalled`. If
the FT Edit feed fails, every FT item counts as paywalled, so the brief never promises an
article opens when it may not. The feed has the same `https://www.ft.com/content/<id>` links as
the rest of ft.com, so that is the link the brief uses.

The brief covers what was published since the previous one (24 hours for the first, at most 72),
and also every FT Edit pick that is new since the last brief, whenever it was published (the
FT often publishes a pick the day before it is chosen); `state.json` keeps the FT Edit ids the
last brief saw, so each pick is offered once.

## Which model writes it

Claude first (`claude-opus-5-5`), then Gemini, then OpenAI. A model is skipped when it has no
key, errors, times out, declines, gets cut off, or answers with something that doesn't hold up
(unknown story ids, no stories). The brief's footer says which model wrote it. If none can, the
brief still goes out with the outlets' own headlines and standfirsts, newest first, no weights,
each with its outlet and access label, and the push says so. A ChatGPT subscription (Go, Plus) has no API access: the OpenAI step needs an
API key from platform.openai.com.

Rough cost: one request a day, 30,000 to 90,000 tokens in (about 150 to 450 items from all the
outlets; a quiet Sunday was 175 items, 28,000 tokens) and 5,000 to 15,000 out (thinking
included). With Claude Opus 5.5 at $4 and $20 per million that is about 25 to 65 cents a day,
so $8 to $20 a month. `ANTHROPIC_EFFORT=low` spends less.

## Written by an agent

With `BRIEF_MODE=external`, `serve` keeps the pages, the archive, `/healthz` and `/readyz`, but
writes no brief and calls no model API. An agent on the same machine writes it instead, through
the container, in two steps:

```
docker exec news-brief python -m brief fetch > items.json
#   ... the agent writes answer.json ...
docker exec -i news-brief python -m brief ingest --model claude < answer.json
```

`fetch` reads the feeds over the same window as the daily run and prints one JSON object:
`brief` (the date, the window's start and end, the time zone, whether it is a weekend, any feed
that failed), `instructions` (`how`: what to do; `system` and `schema`: the editor's rules and
the answer's JSON schema, exactly what a model API is sent, from `brief/prompt.py`), and
`items` (id, source, access (`free`, `unlocked` or `paywalled`), via (`FT Edit` when
unlocked), headline, standfirst, sections, link and time of each item). `brief.unlocked` lists
the FT Edit ids. It keeps the items in `/data/pending.json`, so the answer is checked against
exactly what the agent saw.
`--output <path>` writes the JSON to a file instead. If every feed fails it exits 1 and pushes
that, as the daily run does, unless `--no-push`.

`ingest` reads the answer on stdin (or `--input <path>`) and checks it against
`pending.json`: every key the schema asks for and no others, only ids from the items, each id
once, a `source` on every story, line and read equal to its id's source, a readable id for a
story whenever one of its items is readable, weights 2 to 5, one to three topics, at most four
reads, at least one story. When it
doesn't hold up, ingest saves nothing, keeps `pending.json`, prints every problem
(`stories[2].weight must be one of 2, 3, 4, 5, not 7`) on stderr and as `{"ok": false,
"errors": [...]}` on stdout, and exits 2; the agent fixes the answer and runs it again. When it
does, the brief is saved, `pending.json` goes, the push is sent, and it prints a summary:
date, number of stories, top headlines, whether the push went out. With no `pending.json` it
exits 1.

- `--model <label>`: who wrote it, for the footer (*Written by claude.*); "an external agent"
  if not given.
- `--date <YYYY-MM-DD>`: the day it is filed under; the day of the fetch if not given.
- `--no-push`: no ntfy push.
- `--fallback`: no answer is read; the outlets' own headlines go out, labelled, as when no model
  can write it. A window with no items always gives the empty brief this way.

The answer may be wrapped in a Markdown code fence. `python -m brief run` still works with the
model APIs when their keys are set.

## Reading the latest brief

`python -m brief latest --json` (in the container: `docker exec news-brief python -m brief
latest --json`) and `GET /api/latest.json` give the latest brief as JSON: `date`, `issued`,
`page` (its link, when `BRIEF_URL` is set), `writer`, `lead`, `top_headlines` (the first three),
and every story with its summary, weight, topics, place, link, time, `source`, `access`,
`label` (as the page shows it) and `also` (the other reports, each with its url and label),
then `lines` and `reads`, each with `source`, `access` and `label`. Without `--json`, the date and top three headlines as text. Exit 1 or a 404 when there
is no brief yet.

## Run it

Python 3.13.

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env              # fill in at least one API key; export it, or use your shell's dotenv
.venv/bin/python -m brief run --no-push    # write today's brief now, into ./data
.venv/bin/python -m brief serve            # the pages on :4960, and the brief daily at BRIEF_TIME
.venv/bin/python -m brief fetch            # the items and instructions for an agent, as JSON
.venv/bin/python -m brief ingest --model claude < answer.json   # check and publish its answer
.venv/bin/python -m brief latest --json    # the latest brief, as JSON
.venv/bin/python -m brief sample --tweaks  # render samples/sample-brief.json to sample.html, no network
python3 -m unittest discover -s tests -t .
```

`.env.example` lists every setting with a comment.

## The page

Editorial: EB Garamond throughout, a letterspaced nameplate, the lead set large, then a hairline
index. Light and dark follow the phone. `BRIEF_TWEAKS=1` adds a bar for trying fonts, type
scale, headline weight, accent hue, density and motion live; *Show values* gives the CSS to put
back into `brief/render.py`.

## On the homelab

`deploy/compose.yaml` is the service file for the homelab repository (`services/news-brief/`),
with this repository's `.env.example` beside it. Port 4960 on the machine's loopback, a volume
for `/data`, `/healthz` (the process is up) and `/readyz` (503 when the last good brief is more
than 26 hours old, whether `serve` or `ingest` wrote it). See `AGENTS.md` for how a version gets there.

## Layout

```
brief/
  config.py     settings from the environment, and the sources file
  sources.toml  the outlets and their feeds: edit this one
  feeds.py      the feeds: fetch, parse (RSS, Atom), merge, mark free / FT Edit / paywalled, window
  prompt.py     what the model is asked, and the JSON schema of its answer
  llm.py        Claude, Gemini, OpenAI, and the chain that tries them in order
  model.py      the brief as data; checking a model's answer (leniently, or strictly for ingest); topic links
  render.py     the page and the archive, and the tweaks bar
  job.py        one morning: feeds, model, save, push
  external.py   the same morning with an agent as the writer: fetch, then ingest
  scheduler.py  once a day at BRIEF_TIME, catching up after a late start
  server.py     /, /<date>, /archive, /api/latest.json, /healthz, /readyz
  store.py      one JSON file per brief, written whole; pending.json between fetch and ingest
  notify.py     the ntfy push
tests/          unittest, no network
samples/        one real brief, for design work and the tests
deploy/         the homelab's compose file
```
