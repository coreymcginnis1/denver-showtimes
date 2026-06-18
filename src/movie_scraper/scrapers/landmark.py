"""Landmark Mayan via the boxofficeapi `schedule` endpoint — real per-screening times.

The Mayan's showtimes load from a live endpoint the site calls only after a theater is
chosen:

    GET /api/gatsby-source-boxofficeapi/schedule
        ?from=<DATE>T03:00:00&to=<DATE+1>T03:00:00
        &theaters={"id":"X02AK","timeZone":"America/Denver"}

It returns {theaterId: {schedule: {movieId: {date: [ {id, startsAt, tags, screen,
data.ticketing}, ... ]}}}}. We query one cinema-day (3am-3am) at a time and join film
titles/metadata from the `movies` endpoint. Plain httpx works — no browser needed.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

from .base import BaseScraper, http_client, to_int
from ..models import Showtime

log = logging.getLogger(__name__)

THEATER_ID = "X02AK"
BASE = "https://www.landmarktheatres.com/api/gatsby-source-boxofficeapi"
THEATER_PAGE = "https://www.landmarktheatres.com/theaters/x02ak-landmark-mayan-theatre-denver/"
MOVIE_URL = "https://www.landmarktheatres.com/movies/{mid}-{slug}"


class LandmarkScraper(BaseScraper):
    key = "landmark"

    def fetch(self, start: date, end: date) -> list[Showtime]:
        theaters_param = '{"id":"%s","timeZone":"%s"}' % (THEATER_ID, self.cfg.timezone)
        raw: dict[str, list[dict]] = {}
        with http_client() as client:
            client.headers["Referer"] = "https://www.landmarktheatres.com/showtimes/"
            day = start
            while day <= end:
                nxt = day + timedelta(days=1)
                try:
                    resp = client.get(f"{BASE}/schedule", params={
                        "from": f"{day.isoformat()}T03:00:00",
                        "to": f"{nxt.isoformat()}T03:00:00",
                        "theaters": theaters_param,
                    })
                    resp.raise_for_status()
                    schedule = (resp.json().get(THEATER_ID) or {}).get("schedule") or {}
                except Exception as exc:
                    log.warning("landmark: schedule for %s failed: %s", day, exc)
                    day = nxt
                    continue
                for mid, by_date in schedule.items():
                    for shows in by_date.values():
                        raw.setdefault(mid, []).extend(shows)
                day = nxt

            movies: dict[str, dict] = {}
            ids = sorted(raw.keys())
            if ids:
                params = [("basic", "false"), ("castingLimit", "3")] + [("ids", i) for i in ids]
                mr = client.get(f"{BASE}/movies", params=params)
                if mr.status_code == 200:
                    for m in mr.json():
                        movies[str(m["id"])] = m

        showtimes = self.build(raw, movies, start, end)
        log.info("landmark: %d showtimes", len(showtimes))
        return showtimes

    def build(self, raw: dict, movies: dict, start: date, end: date) -> list[Showtime]:
        """Pure transform of `schedule` + `movies` payloads into timed Showtimes."""
        results: list[Showtime] = []
        seen: set[str] = set()
        for mid, shows in raw.items():
            movie = movies.get(str(mid), {})
            title = movie.get("title") or (movie.get("locale") or {}).get("title") or f"Movie {mid}"
            url = self._movie_url(mid, title)
            for sh in shows:
                sid = sh.get("id")
                if sid in seen:
                    continue
                seen.add(sid)
                start_dt = self._parse_start(sh.get("startsAt"))
                if start_dt is None or not (start <= start_dt.date() <= end):
                    continue
                tags = sh.get("tags") or []
                results.append(Showtime(
                    theater=self.key,
                    theater_name=self.theater_cfg.name,
                    film_title=title,
                    start=start_dt,
                    screen=self._screen(sh, tags),
                    fmt=self._fmt(tags),
                    ticket_url=self._ticket_url(sh) or url,
                    film_url=url,
                    poster=movie.get("poster"),
                    rating=movie.get("certificate"),
                    runtime_minutes=self._runtime_min(movie.get("runtime")),
                    director=self._director(movie),
                    year=self._year(movie),
                ))
        return results

    def _parse_start(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value).replace(tzinfo=self.tz)
        except ValueError:
            return None

    @staticmethod
    def _fmt(tags: list[str]) -> str | None:
        for tag in tags:
            if tag.startswith("Format.Projection."):
                fmt = tag.rsplit(".", 1)[-1]
                return None if fmt.lower() == "digital" else fmt  # "Digital" is the default, hide it
        return None

    @staticmethod
    def _screen(sh: dict, tags: list[str]) -> str | None:
        """Auditorium label, e.g. 'Screen 1 · Downstairs' (the Mayan has up/downstairs houses)."""
        name = ((sh.get("screen") or {}).get("name") or "").strip()
        if name.isdigit():
            name = "Screen " + name                 # normalize bare "3" -> "Screen 3"
        location = None
        for tag in tags:
            if tag.startswith("Auditorium.Experience."):
                value = tag.rsplit(".", 1)[-1]
                if value.lower() in ("upstairs", "downstairs"):
                    location = value
                    break
        if name and location:
            return f"{name} · {location}"
        return name or location or None

    @staticmethod
    def _ticket_url(sh: dict) -> str | None:
        ticketing = (sh.get("data") or {}).get("ticketing") or []
        chosen = next((t for t in ticketing if t.get("provider") == "default"), None)
        chosen = chosen or (ticketing[0] if ticketing else None)
        urls = (chosen or {}).get("urls") or []
        return urls[0] if urls else None

    @staticmethod
    def _movie_url(mid: str, title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return MOVIE_URL.format(mid=mid, slug=slug) if slug else THEATER_PAGE

    @staticmethod
    def _runtime_min(runtime) -> int | None:
        n = to_int(runtime)
        if n is None:
            return None
        return round(n / 60) if n > 300 else n   # API gives seconds for real films

    @staticmethod
    def _director(movie: dict) -> str | None:
        nodes = ((movie.get("directors") or {}).get("nodes")) or []
        if not nodes:
            return None
        person = nodes[0].get("person") or {}
        name = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip()
        return name or None

    @staticmethod
    def _year(movie: dict) -> int | None:
        releases = movie.get("releases") or []
        if releases and releases[0].get("releasedAt"):
            return to_int(releases[0]["releasedAt"][:4])
        return None
