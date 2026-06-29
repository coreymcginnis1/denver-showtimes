"""Alamo Drafthouse (Sloans Lake) via the public "mother" schedule API.

drafthouse.com serves an unauthenticated JSON schedule per venue:

    GET /s/mother/v2/schedule/venue/<venue>
        -> {data: {sessions, presentations, formats, sessionAttributes, market, ...}}

Each session carries a local wall-clock showtime (`showTimeClt`), screen number, and
format/attribute slugs; `presentations` maps a session's film slug to its title / poster /
rating. No browser needed — plain httpx. The venue endpoint returns only that venue's
cinema, but we still filter by the venue's cinemaId defensively.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from .base import BaseScraper, http_client
from ..models import Showtime

log = logging.getLogger(__name__)

SCHEDULE_URL = "https://drafthouse.com/s/mother/v2/schedule/venue/{venue}"
DEFAULT_VENUE = "sloans-lake"
DEFAULT_MARKET = "denver"
# Generic projection tags we don't surface as a "format" (hidden like Landmark's "Digital").
_GENERIC_FMT = {"digital", "2d", "2d-digital", "standard"}
# Alamo's sessionAttributes mix film formats (35MM) with programming/ops tags (Kid Friendly,
# Baby Day Show, "Menu Add Special Screening"). Only surface things that are actually a format.
_SPECIAL_FMT = re.compile(
    r"^(?:\d{2,3}\s?mm|imax|dolby(?:\s+cinema)?|atmos|laser|rpx|3d|4dx|screenx)$", re.I)


class AlamoScraper(BaseScraper):
    key = "alamo"

    def fetch(self, start: date, end: date) -> list[Showtime]:
        venue = self.theater_cfg.location or DEFAULT_VENUE
        with http_client() as c:
            r = c.get(SCHEDULE_URL.format(venue=venue))
            r.raise_for_status()
            data = r.json().get("data", {})
        out = self.build(data, venue, start, end)
        log.info("alamo: %d showtimes", len(out))
        return out

    def build(self, data: dict, venue: str, start: date, end: date) -> list[Showtime]:
        market = (data.get("market") or [{}])[0]
        market_slug = market.get("slug") or DEFAULT_MARKET
        cinema_id = next((c.get("id") for c in market.get("cinemas", [])
                          if c.get("slug") == venue), None)

        pres = {p.get("slug"): p for p in data.get("presentations", [])}
        fmt_titles = {f.get("slug"): f.get("title") for f in data.get("formats", [])}
        attr_names = {a.get("slug"): a.get("name") for a in data.get("sessionAttributes", [])}

        results: list[Showtime] = []
        for s in data.get("sessions", []):
            if s.get("isHidden") or (cinema_id and s.get("cinemaId") != cinema_id):
                continue
            raw = s.get("showTimeClt")
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(raw).replace(tzinfo=self.tz)
            except ValueError:
                continue
            if not (start <= dt.date() <= end):
                continue
            slug = s.get("presentationSlug", "")
            show = (pres.get(slug) or {}).get("show", {})
            title = show.get("title") or slug.replace("-", " ").title() or "(untitled)"
            screen = s.get("screenNumber")
            results.append(Showtime(
                theater=self.key,
                theater_name=self.theater_cfg.name,
                film_title=title,
                start=dt,
                screen=f"Screen {screen}" if screen else None,
                fmt=self._fmt(s, fmt_titles, attr_names),
                ticket_url=f"https://drafthouse.com/{market_slug}/show/{slug}" if slug else None,
                poster=self._poster(show),
                rating=show.get("certification") or None,
            ))
        return results

    @staticmethod
    def _poster(show: dict) -> str | None:
        imgs = show.get("posterImages") or []
        return imgs[0].get("uri") if imgs and isinstance(imgs[0], dict) else None

    def _fmt(self, session: dict, fmt_titles: dict, attr_names: dict) -> str | None:
        """Surface special film formats (35MM, 70MM, IMAX, …); drop generic + programming tags."""
        bits: list[str] = []
        for slug in session.get("sessionAttributeSlugs") or []:
            name = (attr_names.get(slug) or slug or "").strip()
            if name and _SPECIAL_FMT.match(name) and name not in bits:
                bits.append(name)
        if not bits:   # fall back to a non-generic projection format (e.g. a "70mm" formatSlug)
            t = (fmt_titles.get(session.get("formatSlug")) or "").strip()
            if t and t.lower() not in _GENERIC_FMT and "digital" not in t.lower():
                bits.append(t)
        return " · ".join(bits) or None
