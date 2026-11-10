"""Orchestrate scrapers -> normalize/filter/dedupe -> build the data.json feed."""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Config, load_config
from . import formats
from .models import Showtime
from .scrapers.alamo import AlamoScraper
from .scrapers.fandango import FandangoScraper
from .scrapers.dairy import DairyScraper
from .scrapers.cu_ifs import CuIfsScraper
from .scrapers.landmark import LandmarkScraper
from .scrapers.sie_eventive import SieScraper
from .omdb import add_scores
from .tmdb import enrich
from .wikipedia import weekly_views

log = logging.getLogger(__name__)

# Scraper classes by name. A theater entry uses its key as the scraper name unless it sets
# `scraper = "..."` (so several theaters can share one class, e.g. the AMC and Regal locations
# all reading from Fandango).
SCRAPERS = {
    "sie": SieScraper,
    "landmark": LandmarkScraper,
    "alamo": AlamoScraper,
    "fandango": FandangoScraper,
    "dairy": DairyScraper,
    "cu_ifs": CuIfsScraper,
}
WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


# Short words kept lowercase mid-title when re-casing an all-caps/all-lowercase title.
_TITLE_SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "of",
                "on", "or", "nor", "the", "to", "v", "vs", "via", "with"}


def _titlecase(t: str) -> str:
    """Title-case a uniformly-cased string, keeping short connector words lowercase."""
    words = t.split(" ")
    out = []
    for i, w in enumerate(words):
        if i and w.lower() in _TITLE_SMALL:
            out.append(w.lower())
        elif w[:1].isalpha():
            out.append(w[:1].upper() + w[1:].lower())
        else:
            out.append(w)
    return " ".join(out)


def recase(t: str) -> str:
    """Even out capitalization so casing variants of a title merge.

    A fully UPPER or lower title becomes Title Case; in a mixed-case title, ALL-CAPS words of 4+
    letters are down-cased ("BLEACH: ..." -> "Bleach: ..."), and so are ALL-CAPS connector words
    ("Terror IN THE Aisles II" -> "Terror in the Aisles II"), while short acronyms (UFC, RRR),
    single letters ("Plan A") and stylized mixed case (GoodFellas) are left alone.
    """
    if t and (t == t.upper() or t == t.lower()) and t.upper() != t.lower():
        return _titlecase(t)

    def small(m: re.Match) -> str:
        w = m.group(0)
        if w.lower() not in _TITLE_SMALL:
            return w
        before = t[:m.start()].rstrip()
        return w.capitalize() if not before or before[-1] in ":–—-(" else w.lower()   # a phrase starts
    t = re.sub(r"\b[A-Z]{2,4}\b", small, t)
    return re.sub(r"\b[A-Z]{4,}\b", lambda m: m.group(0).capitalize(), t)


def normalize_title(title: str, prefixes: list[str] = (), suffixes: list[str] = ()) -> str:
    """Standardize a film title.

    Strips a leading repertory/event series label (e.g. 'Bleak Week: ') and/or a trailing
    event descriptor (e.g. ': The Midnight Mass Experience', ' (2026)', ' 85th Anniversary'),
    then re-cases fully UPPERCASE *or* fully lowercase titles to Title Case so casing variants
    merge (e.g. 'jackass: best and last' -> 'Jackass: Best and Last'). Mixed-case titles and
    real colons (e.g. 'Star Wars: ...') are preserved — only configured labels are stripped.
    """
    t = (title or "").strip()
    if prefixes:
        m = re.match(r"^(?:%s)\s*[:–—-]\s*" % "|".join(prefixes), t, re.I)
        if m:
            t = t[m.end():].strip()
    # Again until nothing changes: tags stack in any order ("The Host 4K Restoration (2026)" needs
    # the year off before the restoration rule can see the end of the title).
    for _ in range(4):
        before = t
        for suffix in suffixes or ():
            t = re.sub(suffix, "", t, flags=re.I).strip()
        if t == before:
            break
    # Safety net: a stripped tag can leave its separator behind ("The Angry Birds Movie:" once
    # the anniversary rule missed the colon form), so drop any dangling ":" / "-" / "–".
    t = re.sub(r"\s*[:–—-]+$", "", t).strip()
    return recase(t) or (title or "").strip()


# Tags that mark a revival. Fandango dates a revival by its re-release, which is no year hint for
# the film: "The Host 4K Restoration" (Nov 2026) would match a 2026 film also called The Host.
_REVIVAL = re.compile(r"restor(?:ation|ed)|remaster|re-?release|re-?issue|\bRE\d{2}\b|anniversary", re.I)


def revival_tagged(raw: str, cleaned: str) -> bool:
    """True if cleanup stripped a revival tag (restoration, re-release, anniversary, …)."""
    return bool(_REVIVAL.search(raw or "")) and not _REVIVAL.search(cleaned or "")


def is_non_film(title: str, drop: list[str]) -> bool:
    """True if the title is a non-film event (mystery screening, watch party, …)."""
    return bool(drop) and any(re.search(p, title, re.I) for p in drop)


def merge_case_variants(shows: list[Showtime]) -> None:
    """Give titles that differ only in letter case one spelling, in place.

    Theaters disagree on small words ("Pickpocket in New York" vs "Pickpocket In New York"),
    which would otherwise list one film twice. The spelling most showtimes use wins (ties go to
    the alphabetically first, so the choice is stable from run to run).
    """
    spellings: dict[str, Counter] = {}
    for s in shows:
        spellings.setdefault(s.film_title.casefold(), Counter())[s.film_title] += 1
    canon = {k: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
             for k, c in spellings.items() if len(c) > 1}
    for s in shows:
        s.film_title = canon.get(s.film_title.casefold(), s.film_title)


# Words that usually mark an event, a broadcast or a special edition rather than a plain film
# title. A new title containing one is flagged for review in the run summary; it is a prompt to
# look, not a rule (plenty of real films contain these words).
_REVIEW_HINTS = re.compile(
    r"\b(?:live|concert|tour|finals?|championship|worlds|vs\.?|screening|presents?|"
    r"reissue|re-?release|remaster(?:ed)?|restor(?:ed|ation)|encore|anniversary|"
    r"edition|cut|episodes?|season|marathon|double feature|triple feature|q\s*&\s*a|"
    r"fan event|sing-?along|quote-?along|experience|in theaters?|nights?)\b"
    r"|[:–—-]\s*$|\(\d{4}\)|<[^>]*>", re.I)


def _plain(t: str) -> str:
    return re.sub(r"[^\w]+", " ", t.casefold()).strip()


def review_titles(new_titles: list[str], films: list[str]) -> list[tuple[str, str]]:
    """New titles worth a look for a cleanup rule, each with the reason, for the run summary.

    Catches the shapes that have needed rules before, so the next one is spotted the week it
    appears instead of after it has cluttered the film list:
      * a label wrapped around another title on the list ("Series: Film" next to "Film"),
      * the same label in front of two or more titles (a new series or presenter label),
      * event/edition words or leftover punctuation (see _REVIEW_HINTS).
    """
    plain = {f: _plain(f) for f in films}
    labels = Counter(f.split(":", 1)[0].strip().casefold() for f in films if ":" in f)
    out = []
    for t in new_titles:
        reasons = []
        pt = plain.get(t, _plain(t))
        for other, po in plain.items():
            if other == t or len(po) < 4:
                continue
            if pt.endswith(" " + po) or pt.startswith(po + " ") or po.endswith(" " + pt) \
                    or po.startswith(pt + " "):
                if re.search(r"[:–—-]", t) or re.search(r"[:–—-]", other):
                    reasons.append(f"variant of “{other}”")
        if ":" in t and labels[t.split(":", 1)[0].strip().casefold()] > 1:
            reasons.append(f"label “{t.split(':', 1)[0].strip()}:” is on several titles")
        m = _REVIEW_HINTS.search(t)
        if m:
            reasons.append(f"contains “{m.group(0).strip() or m.group(0)}”")
        if reasons:
            out.append((t, "; ".join(reasons)))
    return out


_TITLE_FORMAT_RE = re.compile(r"\b(?:on|in)\s+(\d{2})\s?mm\b|\b(?:on|in)\s+(VistaVision)\b", re.I)


def title_format(title: str) -> str | None:
    """Film-gauge format embedded in a title, e.g. 'Interstellar on 35mm' -> '35mm'.

    Captured before normalize_title strips the tag, so the gauge can be moved to the
    showtime's format field instead of being lost.
    """
    m = _TITLE_FORMAT_RE.search(title or "")
    return (f"{m.group(1)}mm" if m.group(1) else "VistaVision") if m else None


_TITLE_LANG_RE = re.compile(r"\(((?:[A-Za-z]+\s+)?(?:Dub(?:bed)?|Sub(?:titled)?))\)\s*$", re.I)


def title_lang(title: str) -> str | None:
    """Language version in a title's closing tag: 'Tokyo Godfathers (Subtitled)' -> 'Subtitled',
    '(Dubbed)' -> 'Dubbed', '(Hindi Dubbed)' -> 'Hindi dub'. Captured before cleanup strips the tag."""
    m = _TITLE_LANG_RE.search(title or "")
    if not m:
        return None
    tag = re.sub(r"(?i)\bdub$", "Dubbed", re.sub(r"(?i)\bsub$", "Subtitled", m.group(1)))
    return formats.language([tag])


def run(config_path: str = "config.toml", only: set[str] | None = None) -> dict:
    cfg = load_config(config_path)
    tz = ZoneInfo(cfg.timezone)
    today = datetime.now(tz).date()
    end = today + timedelta(days=cfg.days_ahead)

    collected: list[Showtime] = []
    failed: list[str] = []
    for key, tc in cfg.theaters.items():
        if not tc.enabled or (only and key not in only):
            continue
        cls = SCRAPERS.get(tc.scraper or key)
        if cls is None:
            log.warning("theater %s: no scraper %r — skipping", key, tc.scraper or key)
            continue
        try:
            rows = cls(cfg, tc, key=key).fetch(today, end)
        except Exception:
            log.exception("scraper %s failed", key)
            rows = []
        if rows:
            collected.extend(rows)
        else:  # no theater is empty for two straight weeks, so treat this as a failure
            log.error("theater %s returned no showtimes — keeping its last published rows", key)
            failed.append(key)

    # Beyond the window: sources that can look far ahead cheaply (Sie, Landmark, Alamo) report
    # months out, so "All dates" shows what's announced (35mm runs, openings). A failure here never
    # fails a theater; the chains (Fandango, a request per day) don't take part.
    if cfg.ahead_days > cfg.days_ahead:
        far = today + timedelta(days=cfg.ahead_days)
        for key, tc in cfg.theaters.items():
            cls = SCRAPERS.get(tc.scraper or key)
            if not tc.enabled or (only and key not in only) or cls is None or key in failed:
                continue
            try:
                rows = cls(cfg, tc, key=key).fetch_ahead(end + timedelta(days=1), far) or []
            except Exception as e:
                log.warning("film look-ahead %s: %s", key, e)
                rows = []
            collected.extend(rows)

    tcfg = cfg.titles
    normalized: list[Showtime] = []
    for s in collected:
        gauge = title_format(s.film_title)   # capture "35mm"/"70mm" before normalize strips it
        if gauge and not s.fmt:
            s.fmt = gauge
        lang = title_lang(s.film_title)      # likewise "(Subtitled)" / "(Dubbed)"
        if lang and not s.lang:
            s.lang = lang
        raw = s.film_title
        s.film_title = normalize_title(s.film_title, tcfg.strip_prefixes, tcfg.strip_suffixes)
        if revival_tagged(raw, s.film_title):
            s.release_date = None   # the re-release date: not the film's year (see _REVIVAL)
        if not is_non_film(s.film_title, tcfg.drop):
            normalized.append(s)
    merge_case_variants(normalized)

    shows = [s for s in normalized if _passes(s, cfg)]
    # An end from the listing's runtime when the theater gave none. No runtime, no end: the page then
    # shows only the start, and its calendar entry alone assumes 2 hours (no guessed end on the page).
    for s in shows:
        if not s.all_day and s.end is None and s.runtime_minutes:
            s.end = s.start + timedelta(minutes=s.runtime_minutes)

    previous = load_feed(cfg.output)
    film_meta, tmdb_ids = standardize_titles(shows, previous, cfg)

    deduped = {s.uid: s for s in shows}   # after renaming, so variants of one film dedupe too
    ordered = sorted(deduped.values(), key=lambda s: (s.start, s.theater, s.film_title))
    carried = _carried_events(previous, failed, today)
    feed = _build_feed(cfg, ordered, tz, carried=carried, stale=failed)
    feed["film_meta"] = {t: m for t, m in film_meta.items() if t in set(feed["films"])}
    if cfg.omdb.enabled:   # off: ratings dropped from the site (see CLAUDE.md "Ratings")
        add_scores(feed["film_meta"], (previous or {}).get("film_meta"))
    if cfg.trending.wikipedia:
        add_wiki_views(feed["film_meta"], (previous or {}).get("film_meta"), today)
    add_trend(feed["film_meta"])
    feed["tmdb_ids"] = tmdb_ids
    feed["openings"] = denver_openings(feed["events"], (previous or {}).get("openings"), today)
    return feed


OPENINGS_KEEP_DAYS = 400   # remember a film's opening this long after it stops playing


def denver_openings(events: list[dict], previous: dict[str, str] | None, today: date) -> dict[str, str]:
    """Each film's Denver opening: the first day it had a showtime at any theater we track.

    This drives the site's Newest sort and its New releases / Repertory filter, instead of
    TMDB's date (often a festival premiere or another country's release) or Fandango's (the
    national, often NY/LA-limited date). A film's opening is the earliest showtime ever seen,
    so it's carried over from the last feed (`previous`, title -> ISO date) and only moves
    earlier. Films no longer playing are forgotten OPENINGS_KEEP_DAYS after they opened.
    """
    out = dict(previous or {})
    for e in events:
        t, d = e["title"], e["start"][:10]
        if t not in out or d < out[t]:
            out[t] = d
    playing = {e["title"] for e in events}
    cutoff = (today - timedelta(days=OPENINGS_KEEP_DAYS)).isoformat()
    return {t: d for t, d in sorted(out.items()) if t in playing or d >= cutoff}


def standardize_titles(shows: list[Showtime], previous: dict | None, cfg: Config):
    """Match each film to TMDB, rename it to TMDB's title, and return its metadata.

    The cleanup rules only have to get a title close enough to match; after that TMDB's name is
    the standard, so every theater's variant of a film ("Friday The 13th Part 4", a stray
    casing or subtitle difference) merges into one entry. Titles TMDB doesn't have (events,
    shorts programs) keep their cleaned-up name.

    Returns (metadata by displayed title, TMDB id by local title). The id map is saved in the
    feed so next week reuses each match instead of searching again.
    """
    previous = previous or {}
    # "Title @theater" overrides: two theaters can show different films under one title (the
    # Alamos' Little Women is the 2019 one, the Dairy's the 1933 one), so that theater's showings
    # are matched on their own. Unmatched, they fall back to the plain title below.
    scoped = {k for k in cfg.tmdb.overrides if " @" in k}
    for s in shows:
        if f"{s.film_title} @{s.theater}" in scoped:
            s.film_title = f"{s.film_title} @{s.theater}"
    by_id = {m["tmdb_id"]: m for m in (previous.get("film_meta") or {}).values() if m.get("tmdb_id")}
    known = {local: by_id.get(i) or {"tmdb_id": i} for local, i in (previous.get("tmdb_ids") or {}).items()}
    found = enrich(year_hints(shows), known, cfg.tmdb.overrides, enabled=cfg.tmdb.enabled)

    # Two different films with the same TMDB title (a revival next to a remake) keep apart by year.
    ids_by_title: dict[str, set] = {}
    for m in found.values():
        if m.get("title"):
            ids_by_title.setdefault(m["title"], set()).add(m["tmdb_id"])

    def display(m: dict) -> str:
        name = recase(m["title"].strip())   # same casing cleanup ("LA BOLA NEGRA" -> "La Bola Negra")
        if len(ids_by_title.get(m["title"], ())) > 1 and m.get("release"):
            return f"{name} ({m['release'][:4]})"
        return name

    rename = {local: display(m) for local, m in found.items() if m.get("title")}
    for s in shows:
        s.film_title = rename.get(s.film_title, s.film_title.split(" @")[0] if s.film_title in scoped else s.film_title)
    film_meta = {rename[local]: m for local, m in found.items() if local in rename}
    tmdb_ids = {local: m["tmdb_id"] for local, m in found.items() if m.get("tmdb_id")}
    return film_meta, tmdb_ids


def add_wiki_views(film_meta: dict[str, dict], previous: dict | None, today: date) -> None:
    """Attach each film's English Wikipedia views for the last 7 days (`wiki_views`), in place.

    If Wikipedia can't be reached this run, a film keeps last run's count (matched by TMDB id).
    """
    old = {m.get("tmdb_id"): m.get("wiki_views") for m in (previous or {}).values() if m.get("wiki_views")}
    views = weekly_views(sorted({m["tmdb_id"] for m in film_meta.values() if m.get("tmdb_id")}), today)
    for m in film_meta.values():
        v = views.get(m.get("tmdb_id")) or old.get(m.get("tmdb_id"))
        if v:
            m["wiki_views"] = v


def add_trend(film_meta: dict[str, dict]) -> None:
    """The site's "Trending" score (`trend`, lower = more trending), in place.

    The average of a film's rank by TMDB popularity and its rank by 7-day Wikipedia views, among
    this run's films; a film with no Wikipedia article uses its TMDB rank alone. Tested against
    Letterboxd's popular-this-week list (Nov 2026): 50/50 agreed best (0.90 rank correlation vs
    0.59 for TMDB alone and 0.77 for Wikipedia alone). TMDB is worldwide and counts streaming
    (The Mongoose ranked #3); Wikipedia over-weights big international releases (Ramayana).
    """
    matched = [m for m in film_meta.values() if m.get("tmdb_id")]
    tmdb_rank = {id(m): r for r, m in enumerate(sorted(matched, key=lambda m: -(m.get("popularity") or 0)), 1)}
    wiki = [m for m in matched if m.get("wiki_views")]
    wiki_rank = {id(m): r for r, m in enumerate(sorted(wiki, key=lambda m: -m["wiki_views"]), 1)}
    for m in matched:
        t, w = tmdb_rank[id(m)], wiki_rank.get(id(m))
        m["trend"] = (t + w) / 2 if w else float(t)


def year_hints(shows: list[Showtime]) -> dict[str, int | None]:
    """Each title's release year as the theaters give it, to tell same-titled films apart.

    A year a theater states (Sie, Landmark) beats Fandango's release date, which for a revival
    can be the re-release date. Titles with neither map to None.
    """
    stated: dict[str, int] = {}
    released: dict[str, int] = {}
    for s in shows:
        if s.year:
            stated.setdefault(s.film_title, int(s.year))
        if (s.release_date or "")[:4].isdigit():
            released.setdefault(s.film_title, int(s.release_date[:4]))
    return {s.film_title: stated.get(s.film_title) or released.get(s.film_title) for s in shows}


def _carried_events(previous: dict | None, theaters: list[str], today: date) -> list[dict]:
    """A failed theater's still-upcoming events from the last feed, so it stays on the site.

    The feed lists each poster once per film (on its first showing), so a carried row whose
    poster sat on an earlier row gets it back here; `_build_feed` trims the repeats again.
    """
    if not previous or not theaters:
        return []
    old = previous.get("events", [])
    art: dict[tuple[str, str], str] = {}
    for e in old:
        p = e["extendedProps"].get("poster")
        if p:
            art.setdefault((e["title"], e["extendedProps"]["theater"]), p)
            art.setdefault((e["title"], ""), p)
    out = []
    for e in old:
        x = e["extendedProps"]
        if x["theater"] in theaters and e["start"][:10] >= today.isoformat():
            p = x.get("poster") or art.get((e["title"], x["theater"])) or art.get((e["title"], ""))
            out.append({**e, "extendedProps": {**x, **({"poster": p} if p else {})}})
    return out


def _passes(s: Showtime, cfg: Config) -> bool:
    f = cfg.filters
    title = s.film_title or ""
    if f.title_include and not any(re.search(p, title, re.I) for p in f.title_include):
        return False
    if f.title_exclude and any(re.search(p, title, re.I) for p in f.title_exclude):
        return False
    if f.weekdays:
        allowed = {WEEKDAYS[w[:3].lower()] for w in f.weekdays if w[:3].lower() in WEEKDAYS}
        if s.start.weekday() not in allowed:
            return False
    if not s.all_day:
        hhmm = s.start.strftime("%H:%M")
        if f.earliest and hhmm < f.earliest:
            return False
        if f.latest and hhmm > f.latest:
            return False
    return True


def _build_feed(cfg: Config, shows: list[Showtime], tz: ZoneInfo,
                carried: list[dict] = (), stale: list[str] = ()) -> dict:
    events = [s.to_event() for s in shows] + list(carried)
    events.sort(key=lambda e: (e["start"], e["extendedProps"]["theater"], e["title"]))
    # Each poster once per film: the page gathers a film's posters from all its showings, and
    # repeating the same URL on every showing was over a third of data.json.
    seen: set[tuple[str, str]] = set()
    for e in events:
        p = e["extendedProps"].get("poster")
        if p:
            if (e["title"], p) in seen:
                e["extendedProps"] = {k: v for k, v in e["extendedProps"].items() if k != "poster"}
            else:
                seen.add((e["title"], p))
    films = sorted({e["title"] for e in events}, key=str.lower)

    return {
        "generated_at": datetime.now(tz).isoformat(),
        "timezone": cfg.timezone,
        "theaters": [{"key": k, "name": t.name, "color": t.color, "default_on": t.default_on,
                      "lat": t.lat, "lon": t.lon, **({"site": t.site} if t.site else {})}
                     for k, t in cfg.theaters.items() if t.enabled],
        "films": films,
        "stale_theaters": list(stale),   # failed this run; their events are from the last feed
        "events": events,
    }


def load_feed(path: str | Path) -> dict | None:
    """The feed already on disk, or None if it's missing or unreadable."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def theater_counts(feed: dict | None) -> Counter:
    return Counter(e["extendedProps"]["theater"] for e in (feed or {}).get("events", []))


def render_summary(feed: dict, previous: dict | None, new_titles: list[str] | None = None,
                   review: list[tuple[str, str]] | None = None) -> str:
    """Markdown run report: showtimes per theater vs the last feed, failures, new titles."""
    now, before = theater_counts(feed), theater_counts(previous)
    stale = set(feed.get("stale_theaters", ()))
    lines = ["### Showtimes by theater", "",
             "| Theater | Last feed | This run | Status |", "|---|--:|--:|---|"]
    for t in feed["theaters"]:
        key = t["key"]
        if key in stale:
            status = f"❌ failed, kept {now[key]} from the last feed"
        elif now[key] < before[key] / 2:
            status = "⚠️ dropped by more than half"
        else:
            status = "✅"
        lines.append(f"| {t['name']} | {before[key]} | {now[key]} | {status} |")
    meta = feed.get("film_meta")
    if meta is not None and feed.get("films"):
        missing = [f for f in feed["films"] if f not in meta]
        lines += ["", f"TMDB: matched {len(feed['films']) - len(missing)} of {len(feed['films'])} titles "
                  "(release dates, popularity)."]
        if missing:
            lines += ["Not on TMDB (fine for events and programs; for a real film, add "
                      "`[tmdb.overrides]` in config.toml): " + "; ".join(missing)]
    if review:
        lines += ["", f"### {len(review)} new title(s) that may need a cleanup rule", "",
                  "| Title | Why it was flagged |", "|---|---|"]
        lines += [f"| {t} | {why} |" for t, why in review]
    if new_titles:
        lines += ["", f"### {len(new_titles)} new title(s) to check for cleanup rules", ""]
        lines += [f"- {t}" for t in new_titles]
    return "\n".join(lines) + "\n"


def write_feed(feed: dict, output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8")


def diff_new_titles(films: list[str], known_path: str | Path = "known_titles.txt",
                    update: bool = True) -> list[str]:
    """Titles in `films` not seen before (per known_path), for the weekly "what's new" digest.

    Reads the running list of previously-seen titles, returns the ones that are new (so a
    reviewer only eyeballs new/odd titles instead of the whole list), then folds the current
    titles into the file so they won't be reported again (unless update=False, for dry runs).
    """
    path = Path(known_path)
    known: set[str] = set()
    if path.exists():
        known = {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.lstrip().startswith("#")}
    new = sorted(set(films) - known, key=str.lower)
    if new and update:  # only rewrite when something changed
        allk = sorted(known | set(films), key=str.lower)
        path.write_text(
            "# Titles the scraper has already seen — powers the new-title digest.\n"
            "# Auto-updated each run. Delete a line to re-flag that title, or delete the file to reset.\n"
            + "\n".join(allk) + "\n", encoding="utf-8")
    return new
