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
                30: r(30, "Wildwood", "2026-10-19", pop=752),
                10: dict(r(10, "Gozu", "2003-07-11"), imdb_id="tt0361668"),
                11: r(11, "The Devils", "1971-07-16")},
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
    assert out["Gozu"]["imdb_id"] == "tt0361668"                 # from the full record, for OMDb


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


def test_classify_indie_and_international():
    from movie_scraper.tmdb import classify
    co = lambda *names: [{"name": n} for n in names]
    a24 = classify({"original_language": "en", "budget": 7_000_000, "production_companies": co("A24")})
    assert a24["indie"] and not a24["intl"]
    studio = classify({"original_language": "en", "budget": 25_000_000, "production_companies": co("Warner Bros. Pictures")})
    assert not studio["indie"]                                  # a major studio, even on a small budget
    big = classify({"original_language": "en", "budget": 100_000_000, "production_companies": co("LAIKA")})
    assert not big["indie"]                                     # no major, but a studio-size budget
    toho = classify({"original_language": "ja", "budget": 20_000_000, "production_companies": co("TOHO")})
    assert toho["intl"] and not toho["indie"]                   # non-English: International only
    unknown = classify({"original_language": "en", "production_companies": co("Topic Studios")})
    assert unknown["indie"]                                     # no budget listed, no major


def test_meta_from_keeps_director_countries_and_synopsis():
    m = dict(r(5, "Fatherland", "2026-06-19"), overview="  In 1949, Thomas Mann and his daughter Erika take a road trip.  ",
             production_countries=[{"iso_3166_1": "PL"}, {"iso_3166_1": "DE"}],
             credits={"crew": [{"job": "Director", "name": "Paweł Pawlikowski"}, {"job": "Writer", "name": "Someone"}]})
    out = tmdb.meta_from(m)
    assert out["directors"] == ["Paweł Pawlikowski"]
    assert out["countries"] == ["PL", "DE"]
    assert out["overview"] == "In 1949, Thomas Mann and his daughter Erika take a road trip."
    bare = tmdb.meta_from(r(6, "Gozu", "2003-07-11"))                 # a search result: none of these
    assert bare["directors"] == [] and bare["countries"] == [] and bare["overview"] is None
    assert bare["cast"] == [] and bare["genres"] == []


def test_meta_from_keeps_top_billed_cast_and_genres():
    cast = [{"name": f"Actor {n}", "order": n} for n in (6, 2, 0, 1, 3, 4, 5)] + [{"name": "", "order": 7}]
    m = dict(r(7, "Godzilla Minus Zero", "2026-11-03"), credits={"cast": cast, "crew": []},
             genres=[{"id": 878, "name": "Science Fiction"}, {"id": 27, "name": "Horror"}])
    out = tmdb.meta_from(m)
    assert out["cast"] == ["Actor 0", "Actor 1", "Actor 2", "Actor 3", "Actor 4"]   # billing order, top five
    assert out["genres"] == ["Science Fiction", "Horror"]


def test_override_zero_means_not_on_tmdb():
    client = FakeTmdb(search_results={"Family Reunion": [r(292112, "Family Reunion", "1981-10-11")]},
                      movies={292112: r(292112, "Family Reunion", "1981-10-11")})
    assert lookup({"Family Reunion": None}, {}, {"Family Reunion": 0}, client, workers=1) == {}
    assert client.calls == []                                  # not even searched


def test_scoped_override_keeps_two_films_with_one_title_apart(monkeypatch, cfg):
    cfg = cfg.model_copy(deep=True)
    cfg.tmdb.overrides = {"Little Women @dairy": 39938, "Little Women": 331482}
    found = {"Little Women": {"title": "Little Women", "tmdb_id": 331482, "release": "2019-12-25"},
             "Little Women @dairy": {"title": "Little Women", "tmdb_id": 39938, "release": "1933-11-16"}}
    monkeypatch.setattr(pipeline, "enrich", lambda hints, previous, overrides, enabled=True:
                        {t: m for t, m in found.items() if t in hints})
    shows = [_show("Little Women", "alamo_sloans"), _show("Little Women", "dairy", hour=19), _show("Sans Souci", "dairy")]
    meta, ids = pipeline.standardize_titles(shows, {}, cfg)
    assert [s.film_title for s in shows] == ["Little Women (2019)", "Little Women (1933)", "Sans Souci"]
    assert ids["Little Women @dairy"] == 39938


def test_scoped_title_falls_back_to_plain_when_unmatched(monkeypatch, cfg):
    cfg = cfg.model_copy(deep=True)
    cfg.tmdb.overrides = {"Little Women @dairy": 39938}
    monkeypatch.setattr(pipeline, "enrich", lambda *a, **k: {})   # TMDB unreachable, nothing kept
    shows = [_show("Little Women", "dairy")]
    pipeline.standardize_titles(shows, {}, cfg)
    assert shows[0].film_title == "Little Women"
