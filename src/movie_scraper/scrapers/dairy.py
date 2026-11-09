"""Dairy Arts Center, Boulder (the Boedecker Theater and Gordon Gamm Theater).

thedairy.org runs WordPress with The Events Calendar, whose public REST API lists every event
with its exact start, room, image and page (robots.txt leaves /wp-json/ open; it only fences off
the calendar's endless week/month views):

    GET /wp-json/tribe/events/v1/events?categories=cinema&start_date=...&end_date=...&per_page=50
        -> {events: [{title, start_date, end_date, url, image, venue, categories, tags}], total_pages}

Each showing is its own event, so one ranged request (a page per 50) covers months: this source
takes part in the look-ahead like the Sie and the Alamos.
"""
from __future__ import annotations

import html
import logging
import re
from datetime import date, datetime

from .base import BaseScraper, http_client
from ..models import Showtime

log = logging.getLogger(__name__)

EVENTS_URL = "https://thedairy.org/wp-json/tribe/events/v1/events"
# Not screenings: the monthly Cinema Club talks after a film, youth advisory board meetings.
SKIP = {"cinema-club", "youth-advisory-board"}
_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
# The run's dates ride on the title: "Queen at Sea | Nov. 11 – 14", "Nova ’78 | Dec 29 – Jan 3",
# once with no bar at all: "The History of Concrete November 19 – 23".
_RUN = re.compile(rf"\s*\|?\s*{_MONTH}\s+\d{{1,2}}(?:\s*[–—-]\s*(?:{_MONTH}\s+)?\d{{1,2}})?\s*$", re.I)
_YEAR = re.compile(r"\((\d{4})\)\s*$")


def clean_title(raw: str) -> str:
    t = html.unescape(raw or "").replace("’", "'").strip()
    return _RUN.sub("", t).strip() or t


class DairyScraper(BaseScraper):
    key = "dairy"

    def fetch_ahead(self, start: date, end: date) -> list[Showtime]:
        return self.fetch(start, end)   # one ranged request (a page per 50 showings)

    def fetch(self, start: date, end: date) -> list[Showtime]:
        events: list[dict] = []
        with http_client() as c:
            page = 1
            while True:
                r = c.get(EVENTS_URL, params={"categories": "cinema", "start_date": start.isoformat(),
                                              "end_date": f"{end.isoformat()} 23:59:59", "per_page": 50, "page": page})
                r.raise_for_status()
                data = r.json()
                events.extend(data.get("events") or [])
                if page >= (data.get("total_pages") or 1) or page >= 20:
                    break
                page += 1
        out = self.build(events, start, end)
        log.info("dairy: %d showtimes", len(out))
        return out

    def build(self, events: list[dict], start: date, end: date) -> list[Showtime]:
        out: list[Showtime] = []
        for e in events:
            slugs = {x.get("slug") for x in (e.get("categories") or []) + (e.get("tags") or [])}
            if e.get("hide_from_listings") or e.get("all_day") or slugs & SKIP:
                continue
            try:
                dt = datetime.fromisoformat(e["start_date"]).replace(tzinfo=self.tz)
                stop = datetime.fromisoformat(e["end_date"]).replace(tzinfo=self.tz) if e.get("end_date") else None
            except (KeyError, ValueError):
                continue
            if not (start <= dt.date() <= end):
                continue
            title = clean_title(e.get("title"))
            year = _YEAR.search(title)
            room = html.unescape((e.get("venue") or {}).get("venue") or "")
            out.append(Showtime(
                theater=self.key,
                theater_name=self.theater_cfg.name,
                film_title=title,
                start=dt,
                end=stop if stop and stop > dt else None,
                screen=room if room and room != "Dairy Arts Center" else None,
                lang="Subtitled" if "subtitled" in slugs else None,
                ticket_url=e.get("url") or None,
                poster=(e.get("image") or {}).get("url") or None,
                year=int(year.group(1)) if year else None,
            ))
        return out
