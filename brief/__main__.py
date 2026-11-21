"""python -m brief serve | run | fetch | ingest | latest | sample"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
from datetime import date, datetime
from pathlib import Path

from . import config, external, feeds, job, notify, render, scheduler, server
from .model import Brief, digest
from .store import Store

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "sample-brief.json"
MAX_PROBLEMS = 40  # listed for the agent; the rest are counted


def _day(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a date as YYYY-MM-DD: {value!r}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m brief", description="The FT morning brief.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="the pages, and the brief every day at BRIEF_TIME unless BRIEF_MODE=external")
    run = sub.add_parser("run", help="write today's brief now, with the model APIs")
    run.add_argument("--no-push", action="store_true", help="don't send the ntfy push")

    fetch = sub.add_parser("fetch", help="read the feeds and print the items and instructions for an agent, as JSON")
    fetch.add_argument("--output", metavar="PATH", help="write the JSON here instead of to stdout")
    fetch.add_argument("--no-push", action="store_true", help="don't push when every feed fails")

    ingest = sub.add_parser("ingest", help="check an agent's answer against the fetched items and publish the brief")
    ingest.add_argument("--input", metavar="PATH", help="read the answer from here instead of stdin")
    ingest.add_argument("--model", default="", metavar="LABEL", help="who wrote it, for the footer (e.g. claude)")
    ingest.add_argument("--date", type=_day, metavar="YYYY-MM-DD", help="the day it is for; the fetch's day by default")
    ingest.add_argument("--no-push", action="store_true", help="don't send the ntfy push")
    ingest.add_argument("--fallback", action="store_true", help="publish the FT's own headlines; no answer is read")

    latest = sub.add_parser("latest", help="the latest brief's headlines")
    latest.add_argument("--json", action="store_true", help="the whole brief as JSON: date, lead, stories, summaries")

    sample = sub.add_parser("sample", help="render samples/sample-brief.json to a file, with no network")
    sample.add_argument("--out", default="sample.html")
    sample.add_argument("--tweaks", action="store_true", help="include the tweaks bar")
    return parser


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=1))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # Logs go to stderr, so stdout holds only what a command prints (JSON for fetch, ingest, latest --json).
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    cfg = config.load()

    if args.cmd == "sample":
        brief = Brief.from_dict(json.loads(SAMPLE.read_text(encoding="utf-8")))
        Path(args.out).write_text(render.brief_page(brief, cfg.tz, tweaks=args.tweaks), encoding="utf-8")
        print(args.out)
        return 0

    store = Store(cfg.data_dir)
    if args.cmd == "run":
        try:
            brief = job.run(cfg, store, push=not args.no_push)
        except job.NoFeeds as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"{brief.date}: {len(brief.stories)} stories, written by {brief.writer or 'no model'}")
        for f in brief.failures:
            print(f"  failed: {f}")
        return 0
    if args.cmd == "fetch":
        return _fetch(cfg, store, args)
    if args.cmd == "ingest":
        return _ingest(cfg, store, args)
    if args.cmd == "latest":
        return _latest(cfg, store, args)
    return _serve(cfg, store)


def _fetch(cfg: config.Config, store: Store, args: argparse.Namespace) -> int:
    try:
        out = external.fetch(cfg, store, push=not args.no_push, fetch=feeds.fetch, send=notify.send)
    except job.NoFeeds as exc:
        print(exc, file=sys.stderr)
        return 1
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        logging.info("wrote %s", args.output)
    else:
        print(text)
    return 0


def _ingest(cfg: config.Config, store: Store, args: argparse.Namespace) -> int:
    try:
        _, candidates = external.load_pending(store)
        text = None
        if not args.fallback and candidates:
            text = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
        brief, pushed = external.ingest(cfg, store, text, writer=args.model, day=args.date or "", fallback=args.fallback,
                                        push=not args.no_push, send=notify.send)
    except external.NoPending as exc:
        print(exc, file=sys.stderr)
        _print_json({"ok": False, "errors": [str(exc)]})
        return 1
    except external.Invalid as exc:
        shown = exc.problems[:MAX_PROBLEMS]
        if len(exc.problems) > len(shown):
            shown.append(f"and {len(exc.problems) - len(shown)} more")
        print(f"The answer was not accepted ({exc}). Nothing was saved; {store.pending_path} is kept, so fix "
              "these and run ingest again:", file=sys.stderr)
        for p in shown:
            print(f"- {p}", file=sys.stderr)
        _print_json({"ok": False, "errors": shown, "pending": str(store.pending_path)})
        return 2
    except OSError as exc:
        print(f"Can't read the answer: {exc}", file=sys.stderr)
        _print_json({"ok": False, "errors": [f"can't read the answer: {exc}"]})
        return 1
    _print_json({
        "ok": True,
        "date": brief.date,
        "writer": brief.writer,
        "stories": len(brief.stories),
        "lines": len(brief.lines),
        "reads": len(brief.reads),
        "top_headlines": [s.headline for s in brief.stories[:3]],
        "page": f"{cfg.brief_url}/{brief.date}" if cfg.brief_url else "",
        "pushed": pushed,
    })
    return 0


def _latest(cfg: config.Config, store: Store, args: argparse.Namespace) -> int:
    brief = store.latest()
    if brief is None:
        print("No brief yet.", file=sys.stderr)
        return 1
    if args.json:
        _print_json(digest(brief, cfg.brief_url))
        return 0
    print(f"{brief.date}: {len(brief.stories)} stories, written by {brief.writer or 'no model'}")
    for s in brief.stories[:3]:
        print(f"• {s.headline}")
    return 0


def start_scheduler(cfg: config.Config, store: Store, stop: threading.Event) -> threading.Thread | None:
    """The daily run at BRIEF_TIME; none when BRIEF_MODE=external, where an agent writes the brief."""
    if cfg.mode == "external":
        return None
    has_today = lambda: store.load(datetime.now(cfg.tz).date().isoformat()) is not None  # noqa: E731
    worker = threading.Thread(
        target=scheduler.loop, args=(cfg.run_at, cfg.tz, lambda: job.run(cfg, store), has_today, stop), daemon=True
    )
    worker.start()
    return worker


def _serve(cfg: config.Config, store: Store) -> int:
    stop = threading.Event()
    httpd = server.serve(cfg, store)
    worker = start_scheduler(cfg, store, stop)

    def shutdown(*_: object) -> None:
        stop.set()
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    if worker:
        logging.info("serving on %s:%d; brief daily at %s %s", cfg.host, cfg.port, cfg.run_at.strftime("%H:%M"), cfg.tz.key)
    else:
        logging.info("serving on %s:%d; BRIEF_MODE=external, so the brief comes from `fetch` and `ingest`", cfg.host, cfg.port)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
