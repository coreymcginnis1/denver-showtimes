from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from movie_scraper.config import (
    DEFAULT_DROP, DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES, load_config,
)
from movie_scraper.models import Showtime
from movie_scraper.pipeline import _build_feed, _passes, is_non_film, normalize_title

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


def test_normalize_title_strips_series():
    P = DEFAULT_STRIP_PREFIXES
    assert normalize_title("Bleak Week: The Sweet Hereafter", P) == "The Sweet Hereafter"
    assert normalize_title("Sie/Saw: eXistenZ", P) == "eXistenZ"
    assert normalize_title("Sci-Fi Film Series #1: Jaws", P) == "Jaws"
    assert normalize_title("MEMBERS ONLY Staff Pick: Holes", P) == "Holes"
    assert normalize_title("Member Only Sneak Preview: The Invite", P) == "The Invite"
    assert normalize_title("Fan Faves: Michael", P) == "Michael"


def test_normalize_title_preserves_real_colons():
    P = DEFAULT_STRIP_PREFIXES
    assert normalize_title("Star Wars: The Mandalorian and Grogu", P) == "Star Wars: The Mandalorian and Grogu"
    assert normalize_title("The Amazing Digital Circus: The Last Act", P) == "The Amazing Digital Circus: The Last Act"
    assert normalize_title("Toy Story 5", P) == "Toy Story 5"


def test_normalize_title_strips_suffix_and_caps():
    P, S = DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES
    assert normalize_title("Rocky Horror Picture Show w/ CO's Elusive Ingredient Shadowcast", P, S) == "Rocky Horror Picture Show"
    assert normalize_title("Sleepaway Camp: The Midnight Mass Experience", P, S) == "Sleepaway Camp"
    assert normalize_title("Supergirl Fan First Screenings", P, S) == "Supergirl"
    assert normalize_title("STOP! THAT! TRAIN!", P, S) == "Stop! That! Train!"


def test_is_non_film_drop():
    assert is_non_film("AMC Screen Unseen: June 22", DEFAULT_DROP)
    assert is_non_film("¡GOLAZO!: 2026 Soccer Watch Parties", DEFAULT_DROP)
    assert is_non_film("Tokusatsu Tuesdsay", DEFAULT_DROP)
    assert not is_non_film("Jaws", DEFAULT_DROP)
    assert not is_non_film("The Big Lebowski", DEFAULT_DROP)


def test_build_feed_shape():
    c = fresh_cfg()
    feed = _build_feed(c, [st("A", 19, "amc"), st("B", 20, "sie")], DEN)
    assert {"generated_at", "timezone", "theaters", "films", "events"} <= set(feed)
    assert feed["films"] == ["A", "B"]
    assert len(feed["events"]) == 2
    assert {e["extendedProps"]["theater"] for e in feed["events"]} == {"amc", "sie"}


def test_build_feed_default_films_allowlist():
    c = fresh_cfg()
    c.defaults.films = ["dune", "jaws"]
    feed = _build_feed(c, [st("Dune: Part Two"), st("Jaws"), st("Barbie")], DEN)
    assert feed["default_films"] == ["Dune: Part Two", "Jaws"]  # matched, sorted; Barbie excluded


def test_build_feed_default_films_empty_means_all():
    c = fresh_cfg()
    c.defaults.films = []
    feed = _build_feed(c, [st("Dune")], DEN)
    assert feed["default_films"] is None
