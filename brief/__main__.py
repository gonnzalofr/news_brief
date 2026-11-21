"""python -m brief serve | run | sample"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
from datetime import datetime
from pathlib import Path

from . import config, job, render, scheduler, server
from .model import Brief
from .store import Store

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "sample-brief.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m brief", description="The FT morning brief.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="the pages, and the brief every day at BRIEF_TIME")
    run = sub.add_parser("run", help="write today's brief now")
    run.add_argument("--no-push", action="store_true", help="don't send the ntfy push")
    sample = sub.add_parser("sample", help="render samples/sample-brief.json to a file, with no network")
    sample.add_argument("--out", default="sample.html")
    sample.add_argument("--tweaks", action="store_true", help="include the tweaks bar")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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

    stop = threading.Event()
    httpd = server.serve(cfg, store)
    has_today = lambda: store.load(datetime.now(cfg.tz).date().isoformat()) is not None  # noqa: E731
    worker = threading.Thread(
        target=scheduler.loop, args=(cfg.run_at, cfg.tz, lambda: job.run(cfg, store), has_today, stop), daemon=True
    )
    worker.start()

    def shutdown(*_: object) -> None:
        stop.set()
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    logging.info("serving on %s:%d; brief daily at %s %s", cfg.host, cfg.port, cfg.run_at.strftime("%H:%M"), cfg.tz.key)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
