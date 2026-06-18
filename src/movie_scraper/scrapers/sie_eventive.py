"""Sie FilmCenter via the Eventive public API (clean JSON, no key required).

Endpoint: GET https://api.eventive.org/event_buckets/<bucket>/upcoming?date=<ISO>
Returns `films` (metadata, keyed by id) and `shows_by_day` (day -> film_id ->
screen -> [{id, start_time(UTC), end_time(UTC), start_time_label}]).
`upcoming` returns roughly a week, so we query at weekly offsets to cover the window.
"""
from __future__ import annotations

import base64
import logging
from datetime import date, datetime, timedelta, timezone

from .base import BaseScraper, http_client, to_int
from ..models import Showtime

log = logging.getLogger(__name__)

BUCKET = "5ed7cb60eb909700905eb9e4"
UPCOMING = f"https://api.eventive.org/event_buckets/{BUCKET}/upcoming"
FILM_URL = "https://denverfilm.eventive.org/films/{film_id}"

# Eventive's public/publishable read key (sent by denverfilm.eventive.org as HTTP Basic
# auth, key-as-username + empty password). Safe to embed; re-extract if it ever rotates.
EVENTIVE_PUBLISHABLE_KEY = "285f587b83e6ab326e737e00d62ca378"
_BASIC = "Basic " + base64.b64encode(f"{EVENTIVE_PUBLISHABLE_KEY}:".encode()).decode()


class SieScraper(BaseScraper):
    key = "sie"

    def fetch(self, start: date, end: date) -> list[Showtime]:
        films: dict[str, dict] = {}
        shows_by_day: dict[str, dict] = {}

        query_dates = [start]
        d = start + timedelta(days=7)
        while d <= end:
            query_dates.append(d)
            d += timedelta(days=7)

        with http_client() as client:
            client.headers["Authorization"] = _BASIC
            client.headers["Referer"] = "https://denverfilm.eventive.org/"
            for q in query_dates:
                # Eventive expects a UTC instant with a trailing Z (offsets are rejected).
                iso = (datetime(q.year, q.month, q.day, tzinfo=self.tz)
                       .astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
                resp = client.get(UPCOMING, params={"date": iso})
                resp.raise_for_status()
                data = resp.json()
                for film in data.get("films", []):
                    films[film["id"]] = film
                for day, by_film in (data.get("shows_by_day") or {}).items():
                    dst = shows_by_day.setdefault(day, {})
                    for film_id, by_screen in by_film.items():
                        dst.setdefault(film_id, {}).update(by_screen)

        showtimes = self.build(films, shows_by_day, start, end)
        log.info("sie: %d showtimes", len(showtimes))
        return showtimes

    def build(self, films: dict, shows_by_day: dict, start: date, end: date) -> list[Showtime]:
        """Pure transform of an Eventive `upcoming` payload into Showtimes (no I/O)."""
        results: list[Showtime] = []
        for by_film in shows_by_day.values():
            for film_id, by_screen in by_film.items():
                film = films.get(film_id, {})
                for screen, shows in by_screen.items():
                    for show in shows:
                        st = self._parse(show.get("start_time"))
                        if st is None or not (start <= st.date() <= end):
                            continue
                        results.append(self._build(film, film_id, screen, st,
                                                   self._parse(show.get("end_time"))))
        return results

    def _parse(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(self.tz)
        except ValueError:
            return None

    def _build(self, film, film_id, screen, start, end) -> Showtime:
        details = film.get("details") or {}
        credits = film.get("credits") or {}
        return Showtime(
            theater=self.key,
            theater_name=self.theater_cfg.name,
            film_title=film.get("name") or "(untitled)",
            start=start,
            end=end,
            screen=self._clean_screen(screen),
            ticket_url=FILM_URL.format(film_id=film_id),
            film_url=FILM_URL.format(film_id=film_id),
            poster=film.get("poster_image"),
            runtime_minutes=to_int(details.get("runtime")),
            director=credits.get("director"),
            year=to_int(details.get("year")),
        )

    @staticmethod
    def _clean_screen(screen: str | None) -> str | None:
        if not screen:
            return None
        return screen.replace("Sie FilmCenter - ", "").strip() or None
