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
    # Safety net: a stripped tag can leave its separator behind ("The Angry Birds Movie:" once
    # the anniversary rule missed the colon form), so drop any dangling ":" / "-" / "–".
    t = re.sub(r"\s*[:–—-]+$", "", t).strip()
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
    merge_case_variants(normalized)

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
