"""OMDb scores, offline: a fake fetch stands in for the API."""
from movie_scraper.omdb import add_scores, scores

RECORD = {"imdbRating": "8.4", "imdbVotes": "12,345", "Metascore": "82",
          "Ratings": [{"Source": "Internet Movie Database", "Value": "8.4/10"},
                      {"Source": "Rotten Tomatoes", "Value": "93%"}]}


def test_scores_parses_omdb_strings():
    assert scores(RECORD) == {"imdb_rating": 8.4, "imdb_votes": 12345, "metascore": 82, "rt": 93}
    assert scores({"imdbRating": "N/A", "imdbVotes": "N/A", "Metascore": "N/A"}) == \
        {"imdb_rating": None, "imdb_votes": None, "metascore": None, "rt": None}


def test_add_scores_looks_up_by_imdb_id_and_keeps_last_run_on_error():
    meta = {"Good": {"imdb_id": "tt1"}, "Broken": {"imdb_id": "tt2"}, "Event": {"tmdb_id": 5}}
    previous = {"Old name": {"imdb_id": "tt2", "imdb_rating": 7.0, "imdb_votes": 900}}

    def fetch(imdb_id):
        if imdb_id == "tt2":
            raise RuntimeError("Request limit reached!")
        return RECORD

    assert add_scores(meta, previous, fetch=fetch, workers=1) == 1   # films with a Metascore
    assert meta["Good"]["metascore"] == 82
    assert meta["Broken"]["imdb_rating"] == 7.0       # matched by IMDb id, even after a rename
    assert "imdb_rating" not in meta["Event"]          # no IMDb id: nothing to look up


def test_add_scores_without_key_keeps_last_runs_scores():
    meta = {"Jaws": {"imdb_id": "tt0073195"}}
    add_scores(meta, {"Jaws": {"imdb_id": "tt0073195", "imdb_rating": 8.1, "metascore": 87}})
    assert meta["Jaws"]["imdb_rating"] == 8.1 and meta["Jaws"]["metascore"] == 87


def test_add_scores_retries_a_timeout_once():
    import httpx
    calls = []

    def fetch(imdb_id):
        calls.append(imdb_id)
        if len(calls) == 1:
            raise httpx.ReadTimeout("The read operation timed out")
        return RECORD

    meta = {"Slow": {"imdb_id": "tt9"}}
    assert add_scores(meta, {}, fetch=fetch, workers=1) == 1
    assert calls == ["tt9", "tt9"] and meta["Slow"]["metascore"] == 82
