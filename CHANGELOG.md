# Changelog

## 0.4.1 (22 Nov 2026)

- A switch at the top right of every page: Auto (follow the device), Light or Dark. The choice is
  remembered in the browser and applied before the page is drawn.

## 0.4.0 (22 Nov 2026)

More opinion and analysis, all free to read.

- New outlets: The Conversation, VoxEU, ProPublica and Rest of World; the Guardian adds its
  opinion section and the long read. (NYT Opinion and Semafor are in `sources.toml`, commented out.)
- "For later" holds up to six reads (was four); `ingest` accepts six.

## 0.3.0 (22 Nov 2026)

More outlets than the FT, each item labelled with where it is from, FT Edit for the FT, and an icon.

- Sources: the FT, BBC, Guardian, DW, Politico Europe, Al Jazeera, CNBC, Ars Technica and
  TechCrunch, all public RSS or Atom, listed in `brief/sources.toml` (or `SOURCES_FILE`).
  `FEEDS` is gone; the FT's sections are in that file.
- FT Edit: FT items in the FT Edit feed are `unlocked` and shown as **FT Edit**; the other FT
  items are shown as **FT · paywalled**. FT Edit picks new since the last brief are offered even
  when published before its window; `state.json` keeps the ids seen.
- The model ranks all outlets together on news value, merges reports of the same event into one
  story that links a readable version, and names the others under *Also reported by*.
- Every story, line and read has a `source`: required in the answer's schema and checked by
  `ingest` against the item's own source. A story whose id is paywalled while one of its `also`
  items is readable is rejected by `ingest` (and swapped by the model API path).
- `fetch` items carry `source`, `access` and `via`; `pending.json` is version 2, so a fetch made
  by 0.2.0 must be run again. `latest --json` and `/api/latest.json` add `source`, `access`,
  `label` and `also` to each item; nothing was removed.
- The headlines-only fallback includes every outlet, with labels.
- An icon: SVG favicon (lighter in dark mode), PNG and ICO fallbacks, apple-touch-icon.
- Briefs saved by earlier versions still load and show **FT**.

## 0.2.0 (21 Nov 2026)

An agent can write the brief instead of the model APIs.

- `BRIEF_MODE=external`: `serve` serves the pages but writes no brief, for an agent on the
  machine that writes it instead of the model APIs.
- `python -m brief fetch`: the window's FT items, the editor's instructions and the answer's
  schema as one JSON object; the items are kept in `/data/pending.json`.
- `python -m brief ingest`: checks an agent's answer against those items, listing every
  problem when it doesn't hold up, then saves and pushes the brief. `--fallback` sends the FT's
  own headlines.
- `python -m brief latest --json` and `GET /api/latest.json`: the latest brief as JSON.

## 0.1.0 (21 Nov 2026)

The first version.

- A brief every morning at `BRIEF_TIME` from the FT's public feeds, with no cap on the number of
  stories: weight, topics, links between related stories, place and time for each; one-line
  smaller news; reads for later.
- Written by Claude (`claude-opus-5-5`), or Gemini, or OpenAI when the one before fails; the FT's
  own headlines when none can.
- The editorial page, light and dark, an archive, and a tweaks bar for design work.
- An ntfy push with the top three headlines; `/healthz` and `/readyz` for the homelab.
