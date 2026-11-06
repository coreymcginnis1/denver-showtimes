"""Command-line entry point: `python -m movie_scraper`."""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter

from .config import load_config
from .pipeline import diff_new_titles, load_feed, render_summary, review_titles, run, write_feed

# The feed was built, but at least one theater failed and kept its last published showtimes.
EXIT_THEATER_FAILED = 3


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="movie-scraper",
        description="Scrape Denver movie showtimes into an interactive-calendar data feed.")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--output", default=None, help="override the output path from config.toml")
    ap.add_argument("--theater", action="append", metavar="KEY",
                    help="only scrape this theater (repeatable), by its key in config.toml")
    ap.add_argument("--dry-run", action="store_true", help="print a summary; do not write the file")
    ap.add_argument("--summary", metavar="PATH",
                    help="append a Markdown run report to this file (e.g. $GITHUB_STEP_SUMMARY)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s")

    cfg = load_config(args.config)
    previous = load_feed(cfg.output)
    feed = run(args.config, only=set(args.theater) if args.theater else None)
    events = feed["events"]
    # A dry run reports which titles would be new without recording them as seen.
    new = diff_new_titles(feed["films"], update=not args.dry_run)
    review = review_titles(new, feed["films"])

    if args.dry_run:
        counts = Counter(e["extendedProps"]["theater"] for e in events)
        print(f"\n{len(events)} events | {len(feed['films'])} films | "
              f"theaters: {dict(counts)}")
        meta = feed.get("film_meta") or {}
        print(f"TMDB matched {len(meta)} films; OMDb: "
              f"{sum(1 for m in meta.values() if m.get('imdb_rating'))} IMDb ratings, "
              f"{sum(1 for m in meta.values() if m.get('metascore'))} Metascores")
        top = sorted((m for m in meta.values() if (m.get("imdb_votes") or 0) >= 250),
                     key=lambda m: -m["imdb_rating"])[:5]
        for m in top:
            print(f"  IMDb {m['imdb_rating']} ({m['imdb_votes']:,} votes) · MC {m.get('metascore')} · {m['title']}")
        # Every film's match, so a PR reviewer can spot a wrong TMDB match (fix: [tmdb.overrides]).
        print("\nFilm matches (title | TMDB id | release | IMDb id | IMDb rating/votes | Metascore):")
        for t in feed["films"]:
            m = meta.get(t)
            if m:
                print(f"  MATCH | {t} | {m.get('tmdb_id')} | {m.get('release') or ''} | {m.get('imdb_id') or ''} | "
                      f"{m.get('imdb_rating') or ''}/{m.get('imdb_votes') or ''} | {m.get('metascore') or ''}")
            else:
                print(f"  MATCH | {t} | (not on TMDB)")
        for e in events[:12]:
            tag = "all-day" if e["allDay"] else e["start"][11:16]
            print(f"  {e['start'][:10]} {tag:>7}  [{e['extendedProps']['theater']:<8}] {e['title']}")
        if len(events) > 12:
            print(f"  … and {len(events) - 12} more")
    else:
        output = args.output or cfg.output
        write_feed(feed, output)
        print(f"Wrote {len(events)} events to {output}")

    if new:
        print(f"\n{len(new)} new title(s) since last run — eyeball these for cleanup:")
        for t in new:
            print(f"  • {t}")
        if not args.dry_run:
            print("(added to known_titles.txt; they won't be flagged again next week)")
    else:
        print("\nNo new titles since last run.")
    if review:
        print(f"\n{len(review)} of them may need a cleanup rule:")
        for t, why in review:
            print(f"  • {t} — {why}")

    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as f:
            f.write(render_summary(feed, previous, new, review))

    if feed["stale_theaters"]:
        print(f"\nFAILED: {', '.join(feed['stale_theaters'])} returned no showtimes; "
              "kept their last published rows.", file=sys.stderr)
        return EXIT_THEATER_FAILED
    return 0


if __name__ == "__main__":
    sys.exit(main())
