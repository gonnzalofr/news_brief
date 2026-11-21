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

## Run it

Python 3.13.

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env              # fill in at least one API key; export it, or use your shell's dotenv
.venv/bin/python -m brief run --no-push    # write today's brief now, into ./data
.venv/bin/python -m brief serve            # the pages on :4960, and the brief daily at BRIEF_TIME
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
than 26 hours old). See `AGENTS.md` for how a version gets there.

## Layout

```
brief/
  config.py     settings from the environment
  feeds.py      the FT feeds: fetch, parse, merge, window
  prompt.py     what the model is asked, and the JSON schema of its answer
  llm.py        Claude, Gemini, OpenAI, and the chain that tries them in order
  model.py      the brief as data; checking a model's answer; topic links
  render.py     the page and the archive, and the tweaks bar
  job.py        one morning: feeds, model, save, push
  scheduler.py  once a day at BRIEF_TIME, catching up after a late start
  server.py     /, /<date>, /archive, /healthz, /readyz
  store.py      one JSON file per brief, written whole
  notify.py     the ntfy push
tests/          unittest, no network
samples/        one real brief, for design work and the tests
deploy/         the homelab's compose file
```
