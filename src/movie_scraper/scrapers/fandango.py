"""AMC and Regal showtimes via Fandango's public napi JSON.

Both chains' own sites block scrapers: regmovies.com is Cloudflare-gated and only server-renders
the current day, and amctheatres.com bot-challenges headless browsers. Both sell tickets through
Fandango, so we read showtimes from there instead. Its

    GET /napi/theaterMovieShowtimes/<theaterId>?startDate=YYYY-MM-DD&isdesktop=true
        -> {viewModel: {movies: [{title, rating, poster, variants: [{filmFormatHeader,
            amenityGroups: [{showtimes: [{ticketingDate, ticketingJumpPageURL, ...}]}]}]}]}}

endpoint is plain JSON over httpx (no browser, no challenge). One call per date. `location`
is the Fandango theater id (AAFXW = Regal UA Colorado Center, AAJJG = Regal UA Denver Pavilions,
AAYUA = AMC 9+CO 10, AAECN = AMC Westminster Promenade 24).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from .base import BaseScraper, http_client
from ..models import Showtime

log = logging.getLogger(__name__)

SHOWTIMES_URL = "https://www.fandango.com/napi/theaterMovieShowtimes/{tid}"
DEFAULT_TID = "AAFXW"
# Format headers we don't surface (the default 2D screen); keep IMAX / RPX / Premium / 3D / Dolby.
_GENERIC_FMT = {"", "standard", "standard format", "2d"}
# Fandango's header only says "Premium Format"; the showtime group's amenities name the screen.
# Amenity name (lowercased) -> the label the site shows. Laser projection, seating, captions and
# languages are not formats and are ignored.
_SCREENS = [("imax", "IMAX"), ("dolby cinema", "Dolby Cinema"), ("prime at amc", "AMC Prime"),
            ("4dx", "4DX"), ("screenx", "ScreenX"), ("rpx", "RPX"), ("ciné xl", "Ciné XL"), ("cine xl", "Ciné XL")]


class FandangoScraper(BaseScraper):
    key = "fandango"

    def fetch(self, start: date, end: date) -> list[Showtime]:
        tid = (self.theater_cfg.location or DEFAULT_TID).upper()
        results: list[Showtime] = []
        with http_client() as c:
            c.headers["Referer"] = "https://www.fandango.com/"
            day = start
            while day <= end:
                vm = self._get_day(c, tid, day)
                if vm is not None:
                    results.extend(self.parse_day(vm, start, end))
                day += timedelta(days=1)
        log.info("fandango %s: %d showtimes", tid, len(results))
        return results

    def _get_day(self, c, tid: str, day: date) -> dict | None:
        try:
            r = c.get(SHOWTIMES_URL.format(tid=tid),
                      params={"startDate": day.isoformat(), "isdesktop": "true"})
            r.raise_for_status()
            return r.json().get("viewModel", {})
        except Exception as e:
            log.warning("fandango %s %s: %s", tid, day, e)
            return None

    def parse_day(self, vm: dict, start: date, end: date) -> list[Showtime]:
        out: list[Showtime] = []
        for m in vm.get("movies", []) or []:
            title = (m.get("title") or "").strip()
            if not title:
                continue
            poster = self._poster(m)
            rating = m.get("rating") or None
            runtime = m.get("runtime") or None
            release = (m.get("releaseDate") or "")[:10] or None
            for v in m.get("variants", []) or []:
                for ag in v.get("amenityGroups", []) or []:
                    fmt = self._fmt(v, ag)
                    for st in ag.get("showtimes", []) or []:
                        if st.get("expired"):
                            continue
                        dt = self._parse_dt(st.get("ticketingDate"))
                        if dt is None or not (start <= dt.date() <= end):
                            continue
                        out.append(Showtime(
                            theater=self.key,
                            theater_name=self.theater_cfg.name,
                            film_title=title,
                            start=dt,
                            fmt=fmt,
                            ticket_url=st.get("ticketingJumpPageURL") or None,
                            poster=poster,
                            rating=rating,
                            runtime_minutes=runtime or None,
                            release_date=release,
                        ))
        return out

    def _parse_dt(self, raw: str | None) -> datetime | None:
        if not raw:
            return None
        try:                                  # "2026-06-29+19:00" -> local wall-clock
            return datetime.strptime(raw, "%Y-%m-%d+%H:%M").replace(tzinfo=self.tz)
        except ValueError:
            return None

    @staticmethod
    def _fmt(variant: dict, group: dict | None = None) -> str | None:
        """"IMAX", "Dolby Cinema", "4DX 3D", "3D"…; None for a standard 2D showing.

        The variant header is only Standard / Premium Format / 3D, so the named screen comes from
        the amenity group; a premium showing with no recognizable screen stays "Premium Format".
        """
        h = (variant.get("filmFormatHeader") or "").strip()
        if not h or h.lower() in _GENERIC_FMT:
            return None
        names = [(a.get("name") or "").strip().lower() for a in (group or {}).get("amenities") or []]
        screen = next((label for key, label in _SCREENS if any(n.startswith(key) for n in names)), None)
        if h.lower() == "3d":
            return f"{screen} 3D" if screen else "3D"
        return screen or h

    @staticmethod
    def _poster(m: dict) -> str | None:
        sizes = (m.get("poster") or {}).get("size") or {}
        url = sizes.get("300") or sizes.get("200") or sizes.get("full") or None
        if url and url.split("?")[0].rstrip("/").endswith("default_poster.png"):
            return None   # Fandango has no art: its URL *is* the grey placeholder (After Hours)
        # Fandango's renderer takes any width; 600 px stays sharp on 2x screens (cards are ~220 px).
        return url.replace("/ImageRenderer/300/", "/ImageRenderer/600/") if url else None
