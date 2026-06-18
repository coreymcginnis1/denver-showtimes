"""Landmark Mayan via the boxofficeapi (days-only).

Landmark gates exact showtimes behind bot/JS protection that headless scraping
can't reliably reach, so we use the two clean, directly-fetchable endpoints:
  - scheduledMovies?theaterId=X02AK -> which movies play on which days
  - movies?ids=...                  -> title/poster/runtime/rating/director/year
Each (movie, day) becomes an all-day entry linking out to Landmark to buy.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, time

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
        with http_client() as client:
            sched = client.get(f"{BASE}/scheduledMovies", params={"theaterId": THEATER_ID})
            sched.raise_for_status()
            scheduled_days: dict[str, list[str]] = sched.json().get("scheduledDays", {}) or {}

            movies: dict[str, dict] = {}
            ids = list(scheduled_days.keys())
            if ids:
                params = [("basic", "false"), ("castingLimit", "3")] + [("ids", i) for i in ids]
                mr = client.get(f"{BASE}/movies", params=params)
                mr.raise_for_status()
                for m in mr.json():
                    movies[str(m["id"])] = m

        showtimes = self.build(scheduled_days, movies, start, end)
        log.info("landmark: %d day-entries", len(showtimes))
        return showtimes

    def build(self, scheduled_days: dict, movies: dict, start: date, end: date) -> list[Showtime]:
        """Pure transform of scheduledMovies + movies payloads into day-entries (no I/O)."""
        results: list[Showtime] = []
        for mid, days in scheduled_days.items():
            movie = movies.get(str(mid), {})
            title = movie.get("title") or (movie.get("locale") or {}).get("title") or f"Movie {mid}"
            url = self._movie_url(mid, title)
            for day_str in days:
                try:
                    day = date.fromisoformat(day_str[:10])
                except ValueError:
                    continue
                if not (start <= day <= end):
                    continue
                results.append(Showtime(
                    theater=self.key,
                    theater_name=self.theater_cfg.name,
                    film_title=title,
                    start=datetime.combine(day, time(0, 0), tzinfo=self.tz),
                    all_day=True,
                    ticket_url=url,
                    film_url=url,
                    poster=movie.get("poster"),
                    rating=movie.get("certificate"),
                    runtime_minutes=self._runtime_min(movie.get("runtime")),
                    director=self._director(movie),
                    year=self._year(movie),
                    note="Times vary — showtimes & tickets at Landmark",
                ))
        return results

    @staticmethod
    def _movie_url(mid: str, title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return MOVIE_URL.format(mid=mid, slug=slug) if slug else THEATER_PAGE

    @staticmethod
    def _runtime_min(runtime) -> int | None:
        n = to_int(runtime)
        if n is None:
            return None
        return round(n / 60) if n > 300 else n  # API gives seconds for real films

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
