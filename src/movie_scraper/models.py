"""Normalized showtime model shared across scrapers and the data-feed builder."""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Showtime(BaseModel):
    """One screening (or, for days-only sources, one film playing on one day)."""

    theater: str                       # key: "sie" | "landmark" | "amc"
    theater_name: str
    film_title: str
    start: datetime                    # tz-aware (America/Denver); local midnight if all_day
    end: Optional[datetime] = None
    all_day: bool = False              # True for days-only entries (e.g. Landmark)

    screen: Optional[str] = None
    fmt: Optional[str] = None          # e.g. "Dolby Cinema", "35mm"
    ticket_url: Optional[str] = None
    film_url: Optional[str] = None
    poster: Optional[str] = None
    rating: Optional[str] = None
    runtime_minutes: Optional[int] = None
    director: Optional[str] = None
    year: Optional[int] = None
    note: Optional[str] = None

    @property
    def uid(self) -> str:
        """Stable id so re-runs/imports update rather than duplicate."""
        raw = f"{self.theater}|{self.film_title}|{self.start.isoformat()}|{self.all_day}"
        return "ms_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def to_event(self, color: str) -> dict:
        """Shape consumed by FullCalendar in the static frontend."""
        event = {
            "id": self.uid,
            "title": self.film_title,
            "start": self.start.isoformat(),
            "allDay": self.all_day,
            "backgroundColor": color,
            "borderColor": color,
            "extendedProps": {
                "theater": self.theater,
                "theaterName": self.theater_name,
                "screen": self.screen,
                "fmt": self.fmt,
                "ticketUrl": self.ticket_url,
                "filmUrl": self.film_url,
                "poster": self.poster,
                "rating": self.rating,
                "runtime": self.runtime_minutes,
                "director": self.director,
                "year": self.year,
                "note": self.note,
            },
        }
        if self.end is not None:
            event["end"] = self.end.isoformat()
        return event
