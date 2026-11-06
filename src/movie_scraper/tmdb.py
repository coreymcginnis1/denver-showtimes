"""Film metadata from TMDB (themoviedb.org): release date, weekly popularity, rating, poster.

The site sorts films by Newest, Popular this week and Top rated, and these come from TMDB.
Letterboxd's terms forbid scraping and its API is by application only, so TMDB is the source.
TMDB's free API is for non-commercial use with attribution, which the site's footer gives.

Each run looks every film up again so popularity and ratings stay current. A film matched last
week is fetched by its id (stable), a new one is searched by title plus a year hint (the year
Sie/Landmark give, or Fandango's release date), and config overrides fix the rare wrong match.
Nothing here can fail the scrape: without a token, or when TMDB errors, a film keeps last
week's metadata (or none) and the run carries on.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import httpx

log = logging.getLogger(__name__)

API = "https://api.themoviedb.org/3"
POSTER = "https://image.tmdb.org/t/p/w500"   # sharp on 2x screens; cards are ~220 px wide
TOKEN_ENV = "TMDB_TOKEN"


def norm(title: str) -> str:
    """Comparable form of a title: ASCII, lowercase, '&' as 'and', punctuation as spaces."""
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t.replace("&", "and")).strip()


def _year(m: dict) -> int | None:
    d = m.get("release_date") or ""
    return int(d[:4]) if d[:4].isdigit() else None


def pick(title: str, results: list[dict], year: int | None = None) -> dict | None:
    """The TMDB search result that is this film, or None.

    Only an exact title match counts (on the title or original title), or failing that a
    longer TMDB title that starts with ours plus a subtitle ("Zathura" -> "Zathura: A Space
    Adventure"). With a year hint, results within a year of it win (this is what tells the
    1949 "Criss Cross" from a 2014 one). Among what's left, the most popular is the one
    theaters are showing.
    """
    nt = norm(title)
    cands = [m for m in results if nt in (norm(m.get("title", "")), norm(m.get("original_title", "")))]
    if not cands:
        cands = [m for m in results
                 if ":" in m.get("title", "") and norm(m["title"]).startswith(nt + " ")]
    if not cands:
        return None
    if year:
        near = [m for m in cands if _year(m) and abs(_year(m) - year) <= 1]
        if near:
            cands = near
    return max(cands, key=lambda m: m.get("popularity") or 0)


# "Ken Russell's The Devils" -> "The Devils": a possessive credit in front of the title.
_POSSESSIVE = re.compile(r"^[A-Z][\w.\-]*(?:\s+[A-Z][\w.\-]*){0,3}['’]s\s+(?=\S)")


def meta_from(m: dict) -> dict:
    """The fields the site uses, from a TMDB movie or search result."""
    return {
        "title": (m.get("title") or "").strip() or None,
        "tmdb_id": m["id"],
        "release": m.get("release_date") or None,
        "popularity": round(m.get("popularity") or 0, 1),
        "vote_average": round(m.get("vote_average") or 0, 2),
        "vote_count": m.get("vote_count") or 0,
        "tmdb_poster": POSTER + m["poster_path"] if m.get("poster_path") else None,
        "imdb_id": m.get("imdb_id") or None,   # only on full movie records, not search results
    }


class Tmdb:
    def __init__(self, client: httpx.Client):
        self.c = client

    def movie(self, tmdb_id: int) -> dict:
        r = self.c.get(f"/movie/{tmdb_id}")
        r.raise_for_status()
        return r.json()

    def search(self, query: str, year: int | None = None) -> list[dict]:
        params = {"query": query, "include_adult": "false"}
        if year:
            params["year"] = year
        r = self.c.get("/search/movie", params=params)
        r.raise_for_status()
        return r.json().get("results", [])

    def find(self, title: str, year: int | None) -> dict | None:
        m = pick(title, self.search(title, year), year) if year else None
        if m is None:
            m = pick(title, self.search(title), year)
        if m is None:
            base = _POSSESSIVE.sub("", title)
            if base != title:
                m = pick(base, self.search(base), year)
        return m


def lookup(hints: dict[str, int | None], previous: dict[str, dict], overrides: dict[str, int],
           client: Tmdb, workers: int = 8) -> dict[str, dict]:
    """TMDB metadata for each title in `hints` (title -> year hint).

    `previous` is last run's metadata by title: its ids are reused, and it is the fallback when
    a lookup errors. Titles TMDB doesn't have (shorts programs, double features, live events)
    are simply left out.
    """
    def one(title: str):
        known = overrides.get(title) or (previous.get(title) or {}).get("tmdb_id")
        try:
            if not known:   # new title: search, then fetch the full record (it has the IMDb id)
                found = client.find(title, hints.get(title))
                known = found and found["id"]
            return title, meta_from(client.movie(known)) if known else None
        except Exception as e:   # one bad lookup must not sink the rest
            log.warning("tmdb %r: %s — keeping last run's data", title, e)
            return title, previous.get(title)

    with ThreadPoolExecutor(workers) as pool:
        return {t: m for t, m in pool.map(one, sorted(hints)) if m}


def enrich(hints: dict[str, int | None], previous: dict[str, dict], overrides: dict[str, int],
           enabled: bool = True) -> dict[str, dict]:
    """Metadata for this run's films; last run's (for these titles) if TMDB can't be reached."""
    kept = {t: m for t, m in (previous or {}).items() if t in hints}
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not enabled or not hints:
        return kept
    if not token:
        log.warning("%s is not set — skipping TMDB, keeping last run's film data", TOKEN_ENV)
        return kept
    try:
        with httpx.Client(base_url=API, timeout=20,
                          headers={"Authorization": f"Bearer {token}",
                                   "Accept": "application/json"}) as c:
            return lookup(hints, previous or {}, overrides, Tmdb(c))
    except Exception:
        log.exception("TMDB lookup failed — keeping last run's film data")
        return kept
