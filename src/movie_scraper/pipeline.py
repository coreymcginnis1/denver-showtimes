"""Orchestrate scrapers -> normalize/filter/dedupe -> build the data.json feed."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Config, load_config
from .models import Showtime
from .scrapers.alamo import AlamoScraper
from .scrapers.amc import AmcScraper
from .scrapers.fandango import FandangoScraper
from .scrapers.landmark import LandmarkScraper
from .scrapers.sie_eventive import SieScraper

log = logging.getLogger(__name__)

# Scraper classes by name. A theater entry uses its key as the scraper name unless it sets
# `scraper = "..."` (so several theaters can share one class, e.g. two AMCs, or the two Regal
# locations both reading from Fandango).
SCRAPERS = {
    "sie": SieScraper,
    "landmark": LandmarkScraper,
    "amc": AmcScraper,
    "alamo": AlamoScraper,
    "fandango": FandangoScraper,
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
    for suffix in suffixes or ():
        t = re.sub(suffix, "", t, flags=re.I).strip()
    if t and (t == t.upper() or t == t.lower()) and t.upper() != t.lower():
        t = _titlecase(t)   # uniformly UPPER or lower -> Title Case
    elif t:
        # In a mixed-case title, down-case ALL-CAPS words of 4+ letters so casing variants merge
        # ("BLEACH: ..." -> "Bleach: ...", "The LEGO ..." -> "The Lego ..."), while short
        # acronyms (UFC, RRR) and stylized mixed-case are left alone.
        t = re.sub(r"\b[A-Z]{4,}\b", lambda m: m.group(0).capitalize(), t)
    return t or (title or "").strip()


def is_non_film(title: str, drop: list[str]) -> bool:
    """True if the title is a non-film event (mystery screening, watch party, …)."""
    return bool(drop) and any(re.search(p, title, re.I) for p in drop)


_TITLE_FORMAT_RE = re.compile(r"\bon\s+(\d{2,3})\s?mm\b", re.I)


def title_format(title: str) -> str | None:
    """Film-gauge format embedded in a title, e.g. 'Interstellar on 35mm' -> '35mm'.

    Captured before normalize_title strips the tag, so the gauge can be moved to the
    showtime's format field instead of being lost.
    """
    m = _TITLE_FORMAT_RE.search(title or "")
    return f"{m.group(1)}mm" if m else None


def run(config_path: str = "config.toml", only: set[str] | None = None) -> dict:
    cfg = load_config(config_path)
    tz = ZoneInfo(cfg.timezone)
    today = datetime.now(tz).date()
    end = today + timedelta(days=cfg.days_ahead)

    collected: list[Showtime] = []
    for key, tc in cfg.theaters.items():
        if not tc.enabled or (only and key not in only):
            continue
        cls = SCRAPERS.get(tc.scraper or key)
        if cls is None:
            log.warning("theater %s: no scraper %r — skipping", key, tc.scraper or key)
            continue
        try:
            collected.extend(cls(cfg, tc, key=key).fetch(today, end))
        except Exception:
            log.exception("scraper %s failed — skipping it", key)

    tcfg = cfg.titles
    normalized: list[Showtime] = []
    for s in collected:
        gauge = title_format(s.film_title)   # capture "35mm"/"70mm" before normalize strips it
        if gauge and not s.fmt:
            s.fmt = gauge
        s.film_title = normalize_title(s.film_title, tcfg.strip_prefixes, tcfg.strip_suffixes)
        if not is_non_film(s.film_title, tcfg.drop):
            normalized.append(s)

    shows = [s for s in normalized if _passes(s, cfg)]
    for s in shows:  # give timed events an end so add-to-calendar has a duration
        if not s.all_day and s.end is None:
            s.end = s.start + timedelta(minutes=s.runtime_minutes or cfg.default_runtime_minutes)

    deduped = {s.uid: s for s in shows}
    ordered = sorted(deduped.values(), key=lambda s: (s.start, s.theater, s.film_title))
    return _build_feed(cfg, ordered, tz)


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


def _build_feed(cfg: Config, shows: list[Showtime], tz: ZoneInfo) -> dict:
    color_by = {k: t.color for k, t in cfg.theaters.items()}
    films = sorted({s.film_title for s in shows}, key=str.lower)

    # Resolve the default-selection allowlist to concrete titles; None => select all.
    patterns = cfg.defaults.films
    default_films = None
    if patterns:
        rx = [re.compile(p, re.I) for p in patterns]
        default_films = [f for f in films if any(r.search(f) for r in rx)]

    return {
        "generated_at": datetime.now(tz).isoformat(),
        "timezone": cfg.timezone,
        "theaters": [{"key": k, "name": t.name, "color": t.color, "default_on": t.default_on}
                     for k, t in cfg.theaters.items() if t.enabled],
        "films": films,
        "default_films": default_films,
        "events": [s.to_event(color_by.get(s.theater, "#888888")) for s in shows],
    }


def write_feed(feed: dict, output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8")
