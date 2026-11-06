"""Metacritic scores via OMDb (omdbapi.com), keyed by the IMDb id TMDB gives.

The site's only rating is Metacritic (the Top rated sort and "MC 98" on cards). Audience ratings
were tried and dropped: TMDB's come from a few hundred voters, IMDb's own data can't be shown
publicly, Letterboxd forbids scraping, and OMDb's copy of IMDb ratings lags badly for new
releases (Nov 2026: You Can See Everything 7.9 from 165 votes on OMDb vs 9.1 from 27K on IMDb;
41 of 99 films had none). A Metascore is fixed once the reviews are in, so OMDb's copy is
reliable. The IMDb rating and Rotten Tomatoes are still stored, not shown.
OMDb's content is CC BY-NC 4.0 (non-commercial, credited on the site).

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
               fetch=None, workers: int = 2) -> int:
    """Add IMDb/critic scores to each film in `film_meta` that has an IMDb id, in place.

    `previous` is last run's film_meta; a film whose lookup fails (or every film, when there is
    no key) keeps its scores from there. Returns how many films have a Metascore.
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
        return sum(1 for m in film_meta.values() if m.get("metascore"))

    client = None
    if fetch is None:
        client = httpx.Client(timeout=30)   # the free tier is slow; few workers, one retry

        def fetch(imdb_id):
            r = client.get(API, params={"i": imdb_id, "apikey": key})
            r.raise_for_status()
            data = r.json()
            if data.get("Response") == "False":
                raise LookupError(data.get("Error") or "not found")
            return data

    def one(m):
        try:
            try:
                data = fetch(m["imdb_id"])
            except httpx.TransportError:   # timeouts and dropped connections: try once more
                data = fetch(m["imdb_id"])
            m.update(scores(data))
        except Exception as e:   # one bad lookup (or the daily limit) must not sink the rest
            log.warning("omdb %s: %s — keeping last run's ratings", m["imdb_id"], str(e)[:80])
            keep(m)

    try:
        with ThreadPoolExecutor(workers) as pool:
            list(pool.map(one, films))
    finally:
        if client is not None:
            client.close()
    return sum(1 for m in film_meta.values() if m.get("metascore"))
