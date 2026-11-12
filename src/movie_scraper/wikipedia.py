"""English Wikipedia: page views over the last 7 days (half of "Trending") and each film's
Metacritic score as its article reports it (the details panel).

Each film's article is found through Wikidata by its TMDB id (property P4947), so there's no
title matching. Views come from the Wikimedia pageviews API; article text from the MediaWiki
API, 20 articles a request. Both are free and allowed with a descriptive User-Agent, and both
rate-limit GitHub's shared runners, so reads are paced and a 429 waits as asked. Nothing here
raises: a film without an article, or a failed request, just has no value.

Metacritic and Rotten Tomatoes have no free API and forbid scraping (CLAUDE.md "Ratings"); the
score here is the fact as Wikipedia's editors record it, usually within days of release
(Nov 2026: 19 of 30 films in their first two weeks, vs 7 on OMDb).
"""
from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from urllib.parse import quote, unquote

import httpx

log = logging.getLogger(__name__)

SPARQL = "https://query.wikidata.org/sparql"
API = "https://en.wikipedia.org/w/api.php"
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
    # Wikidata gives the article's address, percent-encoded ("Am%C3%A9lie"): decode it to the name.
    return {int(b["tmdb"]["value"]): unquote(b["article"]["value"].rsplit("/", 1)[1])
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


# "{{Metacritic film prose|77|45|...}}" or the usual sentence: "Metacritic, which uses a weighted
# average, assigned the film a score of 77 out of 100 based on 45 critics".
_MC = [re.compile(r"\{\{\s*Metacritic (?:film )?prose\s*\|\s*(?:1\s*=\s*)?(\d{1,3})\b", re.I),
       re.compile(r"\bMetacritic\b[^.]{0,250}?\b(\d{1,3})\s*(?:out of 100|/\s*100)\b", re.I)]
# The film's reviews are under a heading like "Critical response" or "Reception"; looking there
# first keeps a video game's or soundtrack's Metacritic score elsewhere in the article out of it.
_RECEPTION = re.compile(r"^==+\s*(?:Critical (?:response|reception)|Reception|Critical reaction|Response)\s*==+\s*$",
                        re.I | re.M)


def metacritic_in(wikitext: str) -> int | None:
    """The film's Metacritic score (0-100) as its article states it, else None."""
    if not wikitext:
        return None
    h = _RECEPTION.search(wikitext)
    for text in ([wikitext[h.start():]] if h else []) + [wikitext]:
        for pat in _MC:
            m = pat.search(text)
            if m and 0 <= int(m.group(1)) <= 100:
                return int(m.group(1))
    return None


def _get(c: httpx.Client, params: dict) -> dict | None:
    """One API read; on 429 wait as asked (at most a minute) and try again, three tries in all."""
    for _ in range(3):
        try:
            r = c.get(API, params=params)
            if r.status_code == 429:
                time.sleep(min(int(r.headers.get("Retry-After") or 30), 60))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning("wikipedia article read: %s", str(e)[:80])
            time.sleep(5)
    return None


def metascores(tmdb_ids: list[int], pause: float = 2.0, batch: int = 20) -> dict[int, int | None]:
    """Metacritic score per TMDB id, from each film's article.

    A film whose article was read maps to its score, or None when the article gives none; a film
    with no article, or whose read failed, is left out (the caller keeps last run's score).
    """
    out: dict[int, int | None] = {}
    try:
        with httpx.Client(headers=HEADERS, timeout=30) as c:
            found = list(articles(tmdb_ids, c).items())
            for i in range(0, len(found), batch):
                chunk = found[i:i + batch]
                data = _get(c, {"action": "query", "format": "json", "formatversion": "2", "redirects": "1",
                                "prop": "revisions", "rvprop": "content", "rvslots": "main",
                                "titles": "|".join(a.replace("_", " ") for _, a in chunk)})
                if data is not None:
                    q = data.get("query") or {}
                    to = {x["from"]: x["to"] for x in (q.get("normalized") or []) + (q.get("redirects") or [])}
                    text = {p["title"]: ((p.get("revisions") or [{}])[0].get("slots") or {}).get("main", {}).get("content", "")
                            for p in q.get("pages") or [] if not p.get("missing")}
                    for tid, a in chunk:
                        name = a.replace("_", " ")
                        name = to.get(to.get(name, name), to.get(name, name))
                        if name in text:
                            out[tid] = metacritic_in(text[name])
                if i + batch < len(found):
                    time.sleep(pause)
    except Exception:
        log.exception("Wikipedia Metacritic lookup failed")
    return out
