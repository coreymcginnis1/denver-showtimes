"""Command-line entry point: `python -m movie_scraper`."""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter

from .config import load_config
from .pipeline import diff_new_titles, run, write_feed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="movie-scraper",
        description="Scrape Denver movie showtimes into an interactive-calendar data feed.")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--output", default=None, help="override the output path from config.toml")
    ap.add_argument("--theater", action="append", metavar="KEY",
                    help="only scrape this theater (repeatable): sie | landmark | amc")
    ap.add_argument("--dry-run", action="store_true", help="print a summary; do not write the file")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s")

    feed = run(args.config, only=set(args.theater) if args.theater else None)
    events = feed["events"]

    if args.dry_run:
        counts = Counter(e["extendedProps"]["theater"] for e in events)
        print(f"\n{len(events)} events | {len(feed['films'])} films | "
              f"theaters: {dict(counts)}")
        for e in events[:12]:
            tag = "all-day" if e["allDay"] else e["start"][11:16]
            print(f"  {e['start'][:10]} {tag:>7}  [{e['extendedProps']['theater']:<8}] {e['title']}")
        if len(events) > 12:
            print(f"  … and {len(events) - 12} more")
        return 0

    output = args.output or load_config(args.config).output
    write_feed(feed, output)
    print(f"Wrote {len(events)} events to {output}")

    new = diff_new_titles(feed["films"])
    if new:
        print(f"\n{len(new)} new title(s) since last run — eyeball these for cleanup:")
        for t in new:
            print(f"  • {t}")
        print("(added to known_titles.txt; they won't be flagged again next week)")
    else:
        print("\nNo new titles since last run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
