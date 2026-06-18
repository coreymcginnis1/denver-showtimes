from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from movie_scraper.config import load_config
from movie_scraper.models import Showtime
from movie_scraper.pipeline import _build_feed, _passes

DEN = ZoneInfo("America/Denver")
ROOT = Path(__file__).parent.parent


def fresh_cfg():
    return load_config(ROOT / "config.toml")


def st(title="Dune", hour=19, theater="amc", all_day=False):
    return Showtime(theater=theater, theater_name="T", film_title=title,
                    start=datetime(2026, 6, 19, hour, 0, tzinfo=DEN), all_day=all_day)


def test_filter_title_include():
    c = fresh_cfg()
    c.filters.title_include = ["dune"]
    assert _passes(st("Dune: Part Two"), c)
    assert not _passes(st("Barbie"), c)


def test_filter_weekday():
    c = fresh_cfg()
    c.filters.weekdays = ["Fri"]            # 2026-06-19 is a Friday
    assert _passes(st(), c)
    c.filters.weekdays = ["Mon"]
    assert not _passes(st(), c)


def test_filter_time_window():
    c = fresh_cfg()
    c.filters.earliest = "17:00"
    assert _passes(st(hour=19), c)
    assert not _passes(st(hour=12), c)
    # all-day entries are not excluded by a time window
    assert _passes(st(hour=0, all_day=True), c)


def test_build_feed_shape():
    c = fresh_cfg()
    feed = _build_feed(c, [st("A", 19, "amc"), st("B", 20, "sie")], DEN)
    assert {"generated_at", "timezone", "theaters", "films", "events"} <= set(feed)
    assert feed["films"] == ["A", "B"]
    assert len(feed["events"]) == 2
    assert {e["extendedProps"]["theater"] for e in feed["events"]} == {"amc", "sie"}
