"""English Wikipedia: page views over the last 7 days (half of "Trending") and each film's
Metacritic score as its article reports it (the film page). Also, from Wikidata, the language a
film was made in, where TMDB's "original language" is the title's ("In German" on the page).

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


def original_languages(tmdb_ids: list[int]) -> dict[int, str] | None:
    """The language each film was made in, as Wikidata records it ("original language", P364):
    TMDB id -> ISO 639-1 code, for films Wikidata gives exactly one such language. None when
    Wikidata can't be reached (the caller keeps last run's).

    TMDB's original_language follows the original title, so a co-production can get its lead
    producer's language instead of its dialogue's: Fatherland (Ojczyzna, a Polish production
    shot in German) reads "pl", The Fifth Element (French, shot in English) "fr". Films with
    several languages are left out: Wikidata lists them unordered and with minor ones (All About
    My Mother: Catalan, English, Spanish), where TMDB's pick is the main one. So are languages
    without a two-letter code (Cantonese, Mandarin), which TMDB writes its own way ("cn", "zh").
    """
    if not tmdb_ids:
        return {}
    values = " ".join(f'"{i}"' for i in tmdb_ids)
    query = ("SELECT ?tmdb (COUNT(DISTINCT ?l) AS ?n) (SAMPLE(?code) AS ?lang) WHERE { VALUES ?tmdb { %s } "
             "?item wdt:P4947 ?tmdb ; wdt:P364 ?l . OPTIONAL { ?l wdt:P218 ?code } } GROUP BY ?tmdb" % values)
    try:
        with httpx.Client(headers=HEADERS, timeout=30) as c:
            r = c.post(SPARQL, data={"query": query, "format": "json"})
            r.raise_for_status()
            rows = r.json()["results"]["bindings"]
    except Exception:
        log.exception("Wikidata language lookup failed")
        return None
    return {int(b["tmdb"]["value"]): b["lang"]["value"] for b in rows
            if int(b["n"]["value"]) == 1 and b.get("lang")}


def weekly_views(tmdb_ids: list[int], today: date, pause: float = 0.25) -> dict[int, int]:
    """Page views of each film's article over the 7 days ending yesterday (today isn't complete).

    One request at a time with a short pause: Wikimedia rate-limits GitHub's shared runners
    (Nov 12, 2026: 62 of ~170 lookups got 429 with two at once and no pause), and a 429 waits as asked.
    """
    end = today - timedelta(days=1)
    start = end - timedelta(days=6)
    out: dict[int, int] = {}
    try:
        with httpx.Client(headers=HEADERS, timeout=30) as c:
            for tid, article in articles(tmdb_ids, c).items():
                url = VIEWS.format(article=quote(article, safe=""), start=f"{start:%Y%m%d}", end=f"{end:%Y%m%d}")
                data = _get(c, url, what=f"views {article}")
                if data is not None:
                    out[tid] = sum(x["views"] for x in data.get("items", []))
                time.sleep(pause)
    except Exception:
        log.exception("Wikipedia lookup failed")
    return out


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


def _get(c: httpx.Client, url: str, params: dict | None = None, what: str = "article read") -> dict | None:
    """One Wikimedia read. A 429 waits as asked (at most a minute) and a dropped connection waits
    5 s, then it tries again, three tries in all; any other error (a 404: no views yet) gives up."""
    for _ in range(3):
        try:
            r = c.get(url, params=params) if params else c.get(url)
            if r.status_code == 429:
                time.sleep(min(int(r.headers.get("Retry-After") or 30), 60))
                continue
            r.raise_for_status()
            return r.json()
        except httpx.TransportError as e:
            log.warning("wikipedia %s: %s", what, str(e)[:80])
            time.sleep(5)
        except Exception as e:
            log.warning("wikipedia %s: %s", what, str(e)[:80])
            return None
    log.warning("wikipedia %s: still rate-limited, giving up", what)
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
                data = _get(c, API, {"action": "query", "format": "json", "formatversion": "2", "redirects": "1",
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
