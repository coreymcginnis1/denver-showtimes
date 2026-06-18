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
from .scrapers.amc import AmcScraper
from .scrapers.landmark import LandmarkScraper
from .scrapers.sie_eventive import SieScraper

log = logging.getLogger(__name__)

SCRAPERS = {"sie": SieScraper, "landmark": LandmarkScraper, "amc": AmcScraper}
WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def normalize_title(title: str, prefixes: list[str] = (), suffixes: list[str] = ()) -> str:
    """Standardize a film title.

    Strips a leading repertory/event series label (e.g. 'Bleak Week: ') and/or a trailing
    event descriptor (e.g. ': The Midnight Mass Experience'), then title-cases fully
    UPPERCASE titles so casing variants merge. Real titles with a colon (e.g.
    'Star Wars: ...') are preserved because only configured labels are stripped.
    """
    t = (title or "").strip()
    if prefixes:
        m = re.match(r"^(?:%s)\s*[:–—-]\s*" % "|".join(prefixes), t, re.I)
        if m:
            t = t[m.end():].strip()
    for suffix in suffixes or ():
        t = re.sub(suffix, "", t, flags=re.I).strip()
    if t and t.upper() == t and t.lower() != t:   # ALL CAPS -> Title Case
        t = re.sub(r"[A-Za-z]+", lambda mm: mm.group(0).capitalize(), t)
    return t or (title or "").strip()


def is_non_film(title: str, drop: list[str]) -> bool:
    """True if the title is a non-film event (mystery screening, watch party, …)."""
    return bool(drop) and any(re.search(p, title, re.I) for p in drop)


def run(config_path: str = "config.toml", only: set[str] | None = None) -> dict:
    cfg = load_config(config_path)
    tz = ZoneInfo(cfg.timezone)
    today = datetime.now(tz).date()
    end = today + timedelta(days=cfg.days_ahead)

    collected: list[Showtime] = []
    for key, cls in SCRAPERS.items():
        tc = cfg.theaters.get(key)
        if not tc or not tc.enabled or (only and key not in only):
            continue
        try:
            collected.extend(cls(cfg, tc).fetch(today, end))
        except Exception:
            log.exception("scraper %s failed — skipping it", key)

    tcfg = cfg.titles
    normalized: list[Showtime] = []
    for s in collected:
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
        "theaters": [{"key": k, "name": t.name, "color": t.color}
                     for k, t in cfg.theaters.items() if t.enabled],
        "films": films,
        "default_films": default_films,
        "events": [s.to_event(color_by.get(s.theater, "#888888")) for s in shows],
    }


def write_feed(feed: dict, output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8")
