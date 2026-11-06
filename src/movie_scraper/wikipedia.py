"""English Wikipedia page views over the last 7 days, as a possible weekly "Trending" signal.

Experimental (Nov 2026): only `--compare-trending` uses this, to print a side-by-side ranking
against TMDB popularity in a dry run (the PR check). The site doesn't use it yet.

Each film's article is found through Wikidata by its TMDB id (property P4947), so there's no
title matching; views come from the Wikimedia pageviews API. Both are free and allowed with a
descriptive User-Agent. Nothing here raises: a film without an article, or a failed request,
just has no count.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.parse import quote

import httpx

log = logging.getLogger(__name__)

SPARQL = "https://query.wikidata.org/sparql"
VIEWS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/"
         "all-access/user/{article}/daily/{start}00/{end}00")
HEADERS = {"User-Agent": "DenverShowtimes/1.0 (https://coreymcginnis1.github.io/denver-showtimes/)"}


def articles(tmdb_ids: list[int], client: httpx.Client) -> dict[int, str]:
    """English Wikipedia article name for each TMDB id that has one."""
    if not tmdb_ids:
        return {}
    values = " ".join(f'"{i}"' for i in tmdb_ids)
    query = ("SELECT ?tmdb ?article WHERE { VALUES ?tmdb { %s } ?item wdt:P4947 ?tmdb . "
             "?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> . }" % values)
    r = client.post(SPARQL, data={"query": query, "format": "json"})
    r.raise_for_status()
    return {int(b["tmdb"]["value"]): b["article"]["value"].rsplit("/", 1)[1]
            for b in r.json()["results"]["bindings"]}


def weekly_views(tmdb_ids: list[int], today: date, workers: int = 2) -> dict[int, int]:
    """Page views of each film's article over the 7 days ending yesterday (today isn't complete)."""
    end = today - timedelta(days=1)
    start = end - timedelta(days=6)
    try:
        with httpx.Client(headers=HEADERS, timeout=30) as c:
            found = articles(tmdb_ids, c)

            def one(item):
                tid, article = item
                url = VIEWS.format(article=quote(article, safe=""), start=f"{start:%Y%m%d}", end=f"{end:%Y%m%d}")
                try:
                    r = c.get(url)
                    r.raise_for_status()
                    return tid, sum(x["views"] for x in r.json().get("items", []))
                except Exception as e:
                    log.warning("wikipedia views %s: %s", article, str(e)[:80])
                    return tid, None

            with ThreadPoolExecutor(workers) as pool:
                return {t: v for t, v in pool.map(one, found.items()) if v is not None}
    except Exception:
        log.exception("Wikipedia lookup failed")
        return {}
