from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from movie_scraper.config import (
    DEFAULT_DROP, DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES, load_config,
)
from movie_scraper.models import Showtime
from movie_scraper.pipeline import _build_feed, _passes, is_non_film, normalize_title, title_format

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


def test_normalize_title_strips_year_and_event_suffixes():
    P, S = DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES
    assert normalize_title("Moana (2026)", P, S) == "Moana"
    assert normalize_title("Scarface (1983)", P, S) == "Scarface"
    assert normalize_title("Citizen Kane 85th Anniversary", P, S) == "Citizen Kane"
    assert normalize_title("Talladega Nights: Ballad of Ricky Bobby - 20th Anniversary", P, S) == "Talladega Nights: Ballad of Ricky Bobby"
    assert normalize_title("My Neighbor Totoro - Studio Ghibli Fest 2026", P, S) == "My Neighbor Totoro"
    assert normalize_title("MOANA IMAX Opening Night Fan Event", P, S) == "Moana"
    assert normalize_title("Minions & Monsters Early Access Screening", P, S) == "Minions & Monsters"
    # a real number in parens that isn't a 4-digit year is left alone
    assert normalize_title("Se7en", P, S) == "Se7en"


def test_normalize_title_lowercase_to_titlecase():
    assert normalize_title("jackass: best and last") == "Jackass: Best and Last"
    assert normalize_title("the lord of the rings") == "The Lord of the Rings"
    # mixed-case titles are left untouched (only uniform upper/lower get re-cased)
    assert normalize_title("To Wong Foo, Thanks for Everything, Julie Newmar") == "To Wong Foo, Thanks for Everything, Julie Newmar"


def test_is_non_film_drops_soccer_watch_parties():
    assert is_non_film("Argentina vs Cabo Verde - Telemundo presenta la Copa Mundial de la FIFA 2026", DEFAULT_DROP)
    assert is_non_film("Cuartos de Final - Telemundo presenta la Copa Mundial de la FIFA 2026", DEFAULT_DROP)
    assert not is_non_film("Supergirl", DEFAULT_DROP)


def test_normalize_title_series_prefix_and_format_suffix():
    P, S = DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES
    assert normalize_title("The Popcorn List: The Fisherman", P) == "The Fisherman"
    assert normalize_title("Interstellar on 35mm", P, S) == "Interstellar"
    assert normalize_title("Oppenheimer on 70mm", P, S) == "Oppenheimer"


def test_is_non_film_drops_live_broadcast_and_memorial():
    assert is_non_film("F1 on Apple TV Live in IMAX: British Race", DEFAULT_DROP)
    assert is_non_film("Classic - Tim Kaminski Memorial Screening", DEFAULT_DROP)
    assert not is_non_film("F1", DEFAULT_DROP)            # the real 2025 film must survive
    assert not is_non_film("F1: The Movie", DEFAULT_DROP)


def test_title_format_extraction():
    assert title_format("Interstellar on 35mm") == "35mm"
    assert title_format("Oppenheimer on 70mm") == "70mm"
    assert title_format("Interstellar") is None


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


def test_secondary_theaters_config():
    c = fresh_cfg()
    assert c.theaters["amc"].default_on is True             # primary theaters start on
    assert c.theaters["amc_westminster"].default_on is False  # secondary start off
    assert c.theaters["amc_westminster"].scraper == "amc"   # reuses the AMC scraper
    assert c.theaters["alamo_sloans"].default_on is False
    assert c.theaters["regal_colorado"].enabled is False    # Cloudflare-gated -> disabled


def test_build_feed_carries_default_on():
    c = fresh_cfg()
    feed = _build_feed(c, [st("A", 19, "amc")], DEN)
    by_key = {t["key"]: t for t in feed["theaters"]}
    assert by_key["amc"]["default_on"] is True
    assert by_key["amc_westminster"]["default_on"] is False
    assert "regal_colorado" not in by_key                  # disabled theaters omitted from feed
