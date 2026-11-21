# news_brief

A morning brief of world news from the Financial Times, for one reader. Every day at 07:00 it
reads the FT's public feeds, has a model pick and summarise every story worth knowing, keeps the
brief as a page, and pushes the top three headlines to the phone through ntfy. It runs as one
Docker image on the homelab, reached over Tailscale.

## What a brief holds

- **Every story that matters**, with no fixed number: a busy night gives a long brief. Each has a
  short summary, a **weight** from two to five strokes (how far beyond today it is likely to
  matter), its **topics** in small capitals, **links to the other stories** in the same brief
  that share a topic, its place, and the time the FT published it.
- **Also**: smaller news, one line each.
- **For later** (for the weekend on Saturdays and Sundays): analysis and opinion worth reading.
- Every headline links to the article on ft.com, where the subscription applies.

Past briefs stay at `/<date>` and are listed at `/archive`.

## Where the news comes from

The FT's public RSS feeds (`https://www.ft.com/<section>?format=rss`): world, the regions, the
economy, companies, markets, technology, climate and opinion. A feed item has a headline, a
one-line standfirst, a link and a time; that is all the model sees, and the summaries are built
only from it. Nothing here logs in to the FT or reads the full articles: that would mean keeping
the subscription's password on the server, and the FT's terms don't allow automated reading.
The brief covers what was published since the previous one (24 hours for the first, at most 72).

## Which model writes it

Claude first (`claude-opus-5-5`), then Gemini, then OpenAI. A model is skipped when it has no
key, errors, times out, declines, gets cut off, or answers with something that doesn't hold up
(unknown story ids, no stories). The brief's footer says which model wrote it. If none can, the
brief still goes out with the FT's own headlines and standfirsts, newest first, no weights, and
the push says so. A ChatGPT subscription (Go, Plus) has no API access: the OpenAI step needs an
API key from platform.openai.com.

Rough cost: one request a day, 20,000 to 60,000 tokens in and 5,000 to 15,000 out (thinking
included). With Claude Opus 5.5 at $4 and $20 per million that is about 20 to 50 cents a day,
so $6 to $15 a month. `ANTHROPIC_EFFORT=low` spends less.

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
`items` (id, headline, standfirst, sections, link and time of each FT item). It keeps the items
in `/data/pending.json`, so the answer is checked against exactly what the agent saw.
`--output <path>` writes the JSON to a file instead. If every feed fails it exits 1 and pushes
that, as the daily run does, unless `--no-push`.

`ingest` reads the answer on stdin (or `--input <path>`) and checks it against
`pending.json`: every key the schema asks for and no others, only ids from the items, each id
once, weights 2 to 5, one to three topics, at most four reads, at least one story. When it
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
- `--fallback`: no answer is read; the FT's own headlines go out, as when no model can write
  it. A window with no items always gives the empty brief this way.

The answer may be wrapped in a Markdown code fence. `python -m brief run` still works with the
model APIs when their keys are set.

## Reading the latest brief

`python -m brief latest --json` (in the container: `docker exec news-brief python -m brief
latest --json`) and `GET /api/latest.json` give the latest brief as JSON: `date`, `issued`,
`page` (its link, when `BRIEF_URL` is set), `writer`, `lead`, `top_headlines` (the first three),
and every story with its summary, weight, topics, place, link and time, then `lines` and
`reads`. Without `--json`, the date and top three headlines as text. Exit 1 or a 404 when there
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
  config.py     settings from the environment
  feeds.py      the FT feeds: fetch, parse, merge, window
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
