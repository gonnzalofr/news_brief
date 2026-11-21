# Changelog

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
