# Working on news_brief

For anyone, human or coding agent, changing this code. `README.md` says what it does; this file
is how to change it safely. The homelab it runs on has its own rules
(github.com/gonnzalofr/homelab: `CLAUDE.md`, `TODO.md`, `docs/decisions.md`); the ones that
reach here are repeated below.

## Rules

- **This repository is public.** No API key, ntfy topic, tailnet name or password goes in it,
  its history or CI's logs. Real values live only in `.env` on the machine. Look at
  `git status` and the diff before every commit.
- **Only the FT's public feeds.** Don't add a login, a cookie, or scraping of ft.com articles.
  The summaries are built from headline and standfirst only, and the prompt says so; keep it
  that way so the brief never states something the FT didn't.
- **Claude, then Gemini, then OpenAI**, each through its own official SDK (`brief/llm.py`). A
  new provider is one more class with `configured()` and `complete()`, added to `providers()`.
  Any failure moves on to the next; no provider is retried in a loop.
- **A brief always goes out.** If every model fails, the FT's headlines go out instead; only
  every feed failing stops a run, and that is pushed too.
- **Model text is untrusted.** Everything from a model or a feed is escaped in `render.py`, and
  `model.from_model` keeps only ids that were in the input.
- **Exact versions**: `requirements.txt` pins each package; the homelab pins the image tag.
- **Design**: the page's values are custom properties at the top of `render.CSS`; change them
  there, not in component rules. The tweaks bar must keep working (`BRIEF_TWEAKS=1`).
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
