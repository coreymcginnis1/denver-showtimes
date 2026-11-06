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
from .models import Showtime
from .scrapers.alamo import AlamoScraper
from .scrapers.fandango import FandangoScraper
from .scrapers.landmark import LandmarkScraper
from .scrapers.sie_eventive import SieScraper

log = logging.getLogger(__name__)

# Scraper classes by name. A theater entry uses its key as the scraper name unless it sets
# `scraper = "..."` (so several theaters can share one class, e.g. the AMC and Regal locations
# all reading from Fandango).
SCRAPERS = {
    "sie": SieScraper,
    "landmark": LandmarkScraper,
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
    carried = _carried_events(load_feed(cfg.output), failed, today)
    return _build_feed(cfg, ordered, tz, carried=carried, stale=failed)


def _carried_events(previous: dict | None, theaters: list[str], today: date) -> list[dict]:
    """A failed theater's still-upcoming events from the last feed, so it stays on the site."""
    if not previous or not theaters:
        return []
    return [e for e in previous.get("events", [])
            if e["extendedProps"]["theater"] in theaters and e["start"][:10] >= today.isoformat()]


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
    color_by = {k: t.color for k, t in cfg.theaters.items()}
    events = [s.to_event(color_by.get(s.theater, "#888888")) for s in shows] + list(carried)
    events.sort(key=lambda e: (e["start"], e["extendedProps"]["theater"], e["title"]))
    films = sorted({e["title"] for e in events}, key=str.lower)

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


def render_summary(feed: dict, previous: dict | None, new_titles: list[str] | None = None) -> str:
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
    if new_titles:
        lines += ["", f"### {len(new_titles)} new title(s) to check for cleanup rules", ""]
        lines += [f"- {t}" for t in new_titles]
    return "\n".join(lines) + "\n"


def write_feed(feed: dict, output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8")


def diff_new_titles(films: list[str], known_path: str | Path = "known_titles.txt") -> list[str]:
    """Titles in `films` not seen before (per known_path), for the weekly "what's new" digest.

    Reads the running list of previously-seen titles, returns the ones that are new (so a
    reviewer only eyeballs new/odd titles instead of the whole list), then folds the current
    titles into the file so they won't be reported again.
    """
    path = Path(known_path)
    known: set[str] = set()
    if path.exists():
        known = {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.lstrip().startswith("#")}
    new = sorted(set(films) - known, key=str.lower)
    if new:  # only rewrite when something changed
        allk = sorted(known | set(films), key=str.lower)
        path.write_text(
            "# Titles the scraper has already seen — powers the new-title digest.\n"
            "# Auto-updated each run. Delete a line to re-flag that title, or delete the file to reset.\n"
            + "\n".join(allk) + "\n", encoding="utf-8")
    return new
