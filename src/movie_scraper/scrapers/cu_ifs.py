"""CU Boulder's International Film Series, from the university's events calendar.

internationalfilmseries.com refuses automated requests (403 on every page, robots.txt included),
so we don't touch it. The series posts its screenings to CU's official calendar,
calendar.colorado.edu, which runs Localist and has a documented public API (robots.txt allows
it; it only fences off the calendar's HTML views):

    GET /api/2/events?group_id=13934&start=...&end=...&pp=100
        -> {events: [{event: {title, event_instances: [{event_instance: {start, end}}],
                              location_name, url, photo_url, filters: {event_types}}}], page}

Group 13934 is "International Film Series"; `url` is the film's page on the IFS site, which has
prices and tickets. Most but maybe not all IFS screenings reach the campus calendar.
"""
from __future__ import annotations

import html
import logging
import re
import time
from datetime import date, datetime

from .base import BaseScraper, http_client
from ..models import Showtime

log = logging.getLogger(__name__)

EVENTS_URL = "https://calendar.colorado.edu/api/2/events"
IFS_GROUP = 13934
_YEAR = re.compile(r"\((\d{4})\)\s*$")


class CuIfsScraper(BaseScraper):
    key = "cu_ifs"

    def fetch_ahead(self, start: date, end: date) -> list[Showtime]:
        return self.fetch(start, end)   # the whole semester in one request

    def fetch(self, start: date, end: date) -> list[Showtime]:
        events: list[dict] = []
        group = int(self.theater_cfg.location or IFS_GROUP)
        with http_client() as c:
            page = 1
            while True:
                r = c.get(EVENTS_URL, params={"group_id": group, "start": start.isoformat(),
                                              "end": end.isoformat(), "pp": 100, "page": page})
                r.raise_for_status()
                data = r.json()
                events.extend(x.get("event") or {} for x in data.get("events") or [])
                nxt = (data.get("page") or {}).get("next_page")
                if not nxt or page >= 10:
                    break
                page = nxt
                time.sleep(1)   # robots.txt asks for a 1 s crawl delay
        out = self.build(events, start, end)
        log.info("cu_ifs: %d showtimes", len(out))
        return out

    def build(self, events: list[dict], start: date, end: date) -> list[Showtime]:
        out: list[Showtime] = []
        for e in events:
            types = {f.get("name") for f in (e.get("filters") or {}).get("event_types") or []}
            if "Film" not in types:   # the group also posts the odd talk or meeting
                continue
            title = html.unescape(e.get("title") or "").replace("’", "'").strip()
            if not title:
                continue
            year = _YEAR.search(title)
            for inst in e.get("event_instances") or []:
                i = inst.get("event_instance") or {}
                try:
                    dt = datetime.fromisoformat(i["start"]).astimezone(self.tz)
                    stop = datetime.fromisoformat(i["end"]).astimezone(self.tz) if i.get("end") else None
                except (KeyError, ValueError, TypeError):
                    continue
                if i.get("all_day") or not (start <= dt.date() <= end):
                    continue
                out.append(Showtime(
                    theater=self.key,
                    theater_name=self.theater_cfg.name,
                    film_title=title,
                    start=dt,
                    end=stop if stop and stop > dt else None,
                    screen=e.get("location_name") or None,
                    ticket_url=e.get("url") or e.get("localist_url") or None,
                    poster=e.get("photo_url") or None,
                    year=int(year.group(1)) if year else None,
                ))
        return out
