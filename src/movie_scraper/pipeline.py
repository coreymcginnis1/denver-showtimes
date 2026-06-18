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

    shows = [s for s in collected if _passes(s, cfg)]
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
    return {
        "generated_at": datetime.now(tz).isoformat(),
        "timezone": cfg.timezone,
        "theaters": [{"key": k, "name": t.name, "color": t.color}
                     for k, t in cfg.theaters.items() if t.enabled],
        "films": sorted({s.film_title for s in shows}, key=str.lower),
        "events": [s.to_event(color_by.get(s.theater, "#888888")) for s in shows],
    }


def write_feed(feed: dict, output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8")
