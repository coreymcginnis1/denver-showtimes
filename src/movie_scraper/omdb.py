"""IMDb ratings and critic scores via OMDb (omdbapi.com), keyed by the IMDb id TMDB gives.

TMDB's own ratings come from a small community (a few hundred votes for most new releases), so
the site's Top rated sort uses IMDb's audience rating instead, and the Critics sort uses
Metacritic. IMDb's own data files are licensed for personal use only and Letterboxd forbids
scraping, so OMDb is the source: one lookup per film returns the IMDb rating and vote count,
Metascore and Rotten Tomatoes. Its content is CC BY-NC 4.0 (non-commercial, credit on the site).

The key is the OMDB_API_KEY secret. OMDb takes it as a URL parameter, not a header. Lookups are
by exact IMDb id, so there is no title matching here. Like TMDB, nothing here can fail the
scrape: without a key, or when a lookup errors, a film keeps last run's scores.
"""
from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

import httpx

log = logging.getLogger(__name__)

API = "https://www.omdbapi.com/"
KEY_ENV = "OMDB_API_KEY"
FIELDS = ("imdb_rating", "imdb_votes", "metascore", "rt")


def _num(v: str | None, cast=float):
    """OMDb numbers are strings, with "N/A" for missing and commas in vote counts."""
    if not v or v == "N/A":
        return None
    try:
        return cast(re.sub(r"[^\d.]", "", v))
    except ValueError:
        return None


def scores(record: dict) -> dict:
    """The fields the site uses, from an OMDb movie record."""
    rt = next((r.get("Value") for r in record.get("Ratings") or []
               if r.get("Source") == "Rotten Tomatoes"), None)
    return {
        "imdb_rating": _num(record.get("imdbRating")),
        "imdb_votes": _num(record.get("imdbVotes"), int),
        "metascore": _num(record.get("Metascore"), int),
        "rt": _num(rt, int),
    }


def add_scores(film_meta: dict[str, dict], previous: dict[str, dict] | None = None,
               fetch=None, workers: int = 6) -> int:
    """Add IMDb/critic scores to each film in `film_meta` that has an IMDb id, in place.

    `previous` is last run's film_meta; a film whose lookup fails (or every film, when there is
    no key) keeps its scores from there. Returns how many films have an IMDb rating.
    """
    old = {m.get("imdb_id"): m for m in (previous or {}).values() if m.get("imdb_id")}

    def keep(m):
        for k in FIELDS:
            if k in old.get(m.get("imdb_id"), {}):
                m.setdefault(k, old[m["imdb_id"]][k])

    key = os.environ.get(KEY_ENV, "").strip()
    films = [m for m in film_meta.values() if m.get("imdb_id")]
    if fetch is None and not key:
        log.warning("%s is not set — skipping OMDb, keeping last run's ratings", KEY_ENV)
        for m in films:
            keep(m)
        return sum(1 for m in film_meta.values() if m.get("imdb_rating"))

    client = None
    if fetch is None:
        client = httpx.Client(timeout=20)

        def fetch(imdb_id):
            r = client.get(API, params={"i": imdb_id, "apikey": key})
            r.raise_for_status()
            data = r.json()
            if data.get("Response") == "False":
                raise LookupError(data.get("Error") or "not found")
            return data

    def one(m):
        try:
            m.update(scores(fetch(m["imdb_id"])))
        except Exception as e:   # one bad lookup (or the daily limit) must not sink the rest
            log.warning("omdb %s: %s — keeping last run's ratings", m["imdb_id"], str(e)[:80])
            keep(m)

    try:
        with ThreadPoolExecutor(workers) as pool:
            list(pool.map(one, films))
    finally:
        if client is not None:
            client.close()
    return sum(1 for m in film_meta.values() if m.get("imdb_rating"))
