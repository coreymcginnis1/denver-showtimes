"""Regal showtimes via Fandango's public napi JSON.

Regal's own site (regmovies.com) is Cloudflare-gated and only server-renders the current day,
so we read showtimes from Fandango instead — Regal sells tickets through Fandango, and its

    GET /napi/theaterMovieShowtimes/<theaterId>?startDate=YYYY-MM-DD&isdesktop=true
        -> {viewModel: {movies: [{title, rating, poster, variants: [{filmFormatHeader,
            amenityGroups: [{showtimes: [{ticketingDate, ticketingJumpPageURL, ...}]}]}]}]}}

endpoint is plain JSON over httpx (no browser, no challenge). One call per date. `location`
is the Fandango theater id (AAFXW = Regal UA Colorado Center, AAJJG = Regal UA Denver Pavilions).
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
            for v in m.get("variants", []) or []:
                fmt = self._fmt(v)
                for ag in v.get("amenityGroups", []) or []:
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
    def _fmt(variant: dict) -> str | None:
        h = (variant.get("filmFormatHeader") or "").strip()
        return h if h and h.lower() not in _GENERIC_FMT else None

    @staticmethod
    def _poster(m: dict) -> str | None:
        sizes = (m.get("poster") or {}).get("size") or {}
        return sizes.get("300") or sizes.get("200") or sizes.get("full") or None
