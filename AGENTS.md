# Working on news_brief

For anyone, human or coding agent, changing this code. `README.md` says what it does; this file
is how to change it safely. The homelab it runs on has its own rules
(github.com/gonnzalofr/homelab: `CLAUDE.md`, `TODO.md`, `docs/decisions.md`); the ones that
reach here are repeated below.

## Rules

- **This repository is public.** No API key, ntfy topic, tailnet name or password goes in it,
  its history or CI's logs. Real values live only in `.env` on the machine. Look at
  `git status` and the diff before every commit.
- **Only public feeds**, listed in `brief/sources.toml`. Don't add a login, a cookie, an API key
  or scraping of any article page. The summaries are built from headline and standfirst only,
  and the prompt says so; keep it that way so the brief never states something an outlet didn't.
- **The FT is FT Edit.** The reader's licence opens only the FT Edit selection; its public feed
  (`unlocked` in `sources.toml`) marks those items readable, every other FT item is paywalled,
  and when that feed fails all of them are. Never label an item readable without that evidence.
- **Every item shows its outlet.** `source` and `access` come from the feeds, never from the
  model; the model's `source` is only checked against them (`model.problems`).
- **Claude, then Gemini, then OpenAI**, each through its own official SDK (`brief/llm.py`). A
  new provider is one more class with `configured()` and `complete()`, added to `providers()`.
  Any failure moves on to the next; no provider is retried in a loop.
- **Or an agent writes it** (`BRIEF_MODE=external`, `brief/external.py`): `fetch` hands it
  `prompt.SYSTEM`, `prompt.SCHEMA` and `prompt.AGENT`, and `ingest` checks the answer with
  `model.problems` (strict, every problem listed, read from `SCHEMA`) before the same
  `model.from_model`. The editorial rules stay in `prompt.py` for every writer; a rule added to
  `SYSTEM` that can be checked goes in `problems` too.
- **A brief always goes out.** If every model fails, the outlets' headlines go out instead; only
  every feed failing stops a run, and that is pushed too. In external mode that is the
  agent's job (`ingest --fallback` when it can't write one); `/readyz` is the alarm if it doesn't.
- **Model text is untrusted.** Everything from a model or a feed is escaped in `render.py`, and
  `model.from_model` keeps only ids that were in the input.
- **Exact versions**: `requirements.txt` pins each package; the homelab pins the image tag.
- **Design**: the page's values are custom properties at the top of `render.CSS`; change them
  there, not in component rules. The tweaks bar must keep working (`BRIEF_TWEAKS=1`).
  The icon's shapes and colours are in `tools/icons.py`; run it and commit `brief/static/`.
- **Words**: plain and calm, British English, dates as "22 Nov".

## Before you push

```
python3 -m unittest discover -s tests -t .       # no network, no keys
docker build --target runtime .                  # runs the suite again, in the image
```

Commit to `main` with one logical change per commit; the subject says what changed, the body why.

## Releasing to the homelab

1. Move `VERSION`, add the version's section to `CHANGELOG.md`, commit, push.
2. Tag `v<VERSION>` and push the tag: CI publishes `ghcr.io/gonnzalofr/news-brief:<VERSION>`.
3. In the homelab repository: the tag in `services/news-brief/compose.yaml`, then on the
   machine `git pull` and `hosts/apps-vm/up.sh news-brief` (homelab README, *Updating a
   service*). The dev user `work` has no Docker; the deploy is done as `main`.
