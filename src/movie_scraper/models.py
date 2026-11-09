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
    fmt: Optional[str] = None          # formats.canon(): "IMAX", "Dolby 3D", "35mm", "PLF"…
    lang: Optional[str] = None         # formats.language(): "Subtitled", "Dubbed", "Spanish dub"
    ticket_url: Optional[str] = None
    film_url: Optional[str] = None
    poster: Optional[str] = None
    rating: Optional[str] = None
    runtime_minutes: Optional[int] = None
    director: Optional[str] = None
    year: Optional[int] = None
    release_date: Optional[str] = None   # ISO date, when the source gives one (Fandango)
    note: Optional[str] = None

    @property
    def uid(self) -> str:
        """Stable id so re-runs/imports update rather than duplicate."""
        raw = f"{self.theater}|{self.film_title}|{self.start.isoformat()}|{self.all_day}"
        return "ms_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def to_event(self) -> dict:
        """One showtime as the site reads it (`data.json` events). Only fields the site uses are
        written, and empty ones are left out, to keep the daily data file and its history lean."""
        props = {
            "theater": self.theater,
            "screen": self.screen,
            "fmt": self.fmt,
            "lang": self.lang,
            "ticketUrl": self.ticket_url,
            "poster": self.poster,
            "rating": self.rating,
            "runtime": self.runtime_minutes,
            "year": self.year,
            "release": self.release_date,
        }
        event = {
            "id": self.uid,
            "title": self.film_title,
            "start": self.start.isoformat(),
            "extendedProps": {k: v for k, v in props.items() if v not in (None, "")},
        }
        if self.all_day:
            event["allDay"] = True
        if self.end is not None:
            event["end"] = self.end.isoformat()
        return event
