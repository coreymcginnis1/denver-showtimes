"""TMDB matching, offline: a fake client stands in for the API."""
from datetime import datetime
from zoneinfo import ZoneInfo

from movie_scraper import pipeline, tmdb
from movie_scraper.models import Showtime
from movie_scraper.pipeline import year_hints
from movie_scraper.tmdb import lookup, pick


def r(id, title, date, pop=1.0, votes=10, avg=7.0, poster="/p.jpg", original=None):
    return {"id": id, "title": title, "original_title": original or title, "release_date": date,
            "popularity": pop, "vote_count": votes, "vote_average": avg, "poster_path": poster}


def test_pick_uses_year_hint_to_choose_between_same_titles():
    res = [r(1, "Criss Cross", "2014-01-08", pop=1.8), r(2, "Criss Cross", "1949-02-04", pop=1.7)]
    assert pick("Criss Cross", res, 1949)["id"] == 2
    assert pick("Criss Cross", res, None)["id"] == 1          # no hint: most popular


def test_pick_ignores_a_year_hint_nothing_matches():
    # Fandango can give a revival's re-release date; that must not lose the real film.
    res = [r(5, "Drive", "2011-09-15", pop=13)]
    assert pick("Drive", res, 2026)["id"] == 5


def test_pick_requires_a_real_title_match():
    res = [r(1, "Ramayana: Rise of a Legend", "2026-11-05"), r(2, "Voyage to the Mystery Moon", "1966")]
    assert pick("Mystery Voyage", res) is None                # no fuzzy guessing
    assert pick("Zathura", [r(3, "Zathura: A Space Adventure", "2005-11-06")])["id"] == 3
    assert pick("Dive In Wonderland", [r(4, "Dive in Wonderland", "2025-08-29")])["id"] == 4


class FakeTmdb(tmdb.Tmdb):
    def __init__(self, search_results=None, movies=None, fail=()):
        self.search_results, self.movies, self.fail, self.calls = search_results or {}, movies or {}, fail, []

    def search(self, query, year=None):
        self.calls.append(("search", query, year))
        if query in self.fail:
            raise RuntimeError("TMDB down")
        return self.search_results.get(query, [])

    def movie(self, tmdb_id):
        self.calls.append(("movie", tmdb_id))
        return self.movies[tmdb_id]


def test_lookup_matches_reuses_ids_overrides_and_falls_back():
    client = FakeTmdb(
        search_results={"Gozu": [r(10, "Gozu", "2003-07-11")],
                         "The Devils": [r(11, "The Devils", "1971-07-16")],
                         "Broken": []},
        movies={20: r(20, "Dune", "2021-09-15", pop=41, votes=15896, avg=7.8),
                30: r(30, "Wildwood", "2026-10-19", pop=752)},
        fail=("Broken",))
    previous = {"Wildwood": {"tmdb_id": 30, "popularity": 1},
                "Broken": {"tmdb_id": None, "release": "2020-01-01"}}
    hints = {"Gozu": 2003, "Ken Russell's The Devils": None, "Dune: Part One": None,
             "Wildwood": None, "Shorts Package: Mirrors": None, "Broken": None}
    previous["Broken"] = {"release": "2020-01-01"}           # no id: it gets searched, which fails
    out = lookup(hints, previous, {"Dune: Part One": 20}, client, workers=1)

    assert out["Gozu"]["tmdb_id"] == 10 and out["Gozu"]["release"] == "2003-07-11"
    assert out["Ken Russell's The Devils"]["tmdb_id"] == 11     # possessive credit dropped
    assert out["Dune: Part One"]["vote_count"] == 15896          # override fetched by id
    assert out["Wildwood"]["popularity"] == 752                  # last week's id, fresh numbers
    assert ("search", "Wildwood", None) not in client.calls
    assert "Shorts Package: Mirrors" not in out                  # not a film: left out
    assert out["Broken"] == {"release": "2020-01-01"}            # error: keep last week's
    assert out["Gozu"]["tmdb_poster"].startswith("https://image.tmdb.org/")


def test_enrich_without_token_keeps_last_runs_data(monkeypatch):
    monkeypatch.delenv("TMDB_TOKEN", raising=False)
    prev = {"Jaws": {"tmdb_id": 578}, "Gone": {"tmdb_id": 1}}
    assert tmdb.enrich({"Jaws": 1975}, prev, {}) == {"Jaws": {"tmdb_id": 578}}   # only current titles


def _show(title, theater="amc", hour=19, year=None, release=None):
    return Showtime(theater=theater, theater_name="T", film_title=title, year=year, release_date=release,
                    start=datetime(2026, 11, 7, hour, 0, tzinfo=ZoneInfo("America/Denver")))


def test_year_hints_prefer_stated_year_over_release_date():
    hints = year_hints([_show("Goodfellas", release="2026-11-06"), _show("Goodfellas", year=1990),
                        _show("Resident Evil", release="2026-09-16"), _show("Mouse")])
    assert hints == {"Goodfellas": 1990, "Resident Evil": 2026, "Mouse": None}


def test_tmdb_title_becomes_the_standard_and_merges_variants(monkeypatch, cfg):
    found = {
        "Friday The 13th Part 4": {"title": "Friday the 13th: The Final Chapter", "tmdb_id": 9730},
        "Friday the 13th: The Final Chapter": {"title": "Friday the 13th: The Final Chapter", "tmdb_id": 9730},
        "Resident Evil": {"title": "Resident Evil", "tmdb_id": 1, "release": "2026-09-16"},
        "Resident Evil Revival": {"title": "Resident Evil", "tmdb_id": 2, "release": "2002-03-15"},
    }
    seen = {}
    def fake_enrich(hints, previous, overrides, enabled=True):
        seen["previous"] = previous
        return {t: m for t, m in found.items() if t in hints}
    monkeypatch.setattr(pipeline, "enrich", fake_enrich)
    shows = [_show("Friday The 13th Part 4", "regal_pavilions"),
             _show("Friday the 13th: The Final Chapter", "alamo_sloans", hour=21),
             _show("Resident Evil"), _show("Resident Evil Revival", hour=22), _show("Shorts Package: Mirrors")]
    previous = {"tmdb_ids": {"Resident Evil": 1},
                "film_meta": {"Resident Evil": {"title": "Resident Evil", "tmdb_id": 1, "popularity": 9}}}
    meta, ids = pipeline.standardize_titles(shows, previous, cfg)

    titles = [s.film_title for s in shows]
    assert titles[:2] == ["Friday the 13th: The Final Chapter"] * 2          # one film, one entry
    assert titles[2:4] == ["Resident Evil (2026)", "Resident Evil (2002)"]    # same name, kept apart
    assert titles[4] == "Shorts Package: Mirrors"                             # no match: unchanged
    assert set(meta) == {"Friday the 13th: The Final Chapter", "Resident Evil (2026)", "Resident Evil (2002)"}
    assert ids["Friday The 13th Part 4"] == 9730
    assert seen["previous"]["Resident Evil"]["popularity"] == 9               # last week's match reused
