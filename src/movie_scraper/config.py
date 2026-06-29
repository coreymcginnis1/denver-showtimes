"""Load and validate config.toml."""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class TheaterCfg(BaseModel):
    enabled: bool = True             # scrape this theater and include it in the feed
    default_on: bool = True          # whether its filter chip starts ON when the page loads
    name: str
    color: str = "#888888"
    scraper: Optional[str] = None    # which scraper class to use; defaults to the theater key
    location: Optional[str] = None   # scraper-specific id (AMC slug path / Alamo venue / Regal route)


class Filters(BaseModel):
    title_include: list[str] = Field(default_factory=list)
    title_exclude: list[str] = Field(default_factory=list)
    weekdays: list[str] = Field(default_factory=list)       # e.g. ["Fri","Sat","Sun"]
    earliest: Optional[str] = None                          # "HH:MM" local
    latest: Optional[str] = None                            # "HH:MM" local


DEFAULT_STRIP_PREFIXES = [
    r"Bleak Week",
    r"Sie/?Saw",
    r"Sci-?Fi Film Series(?:\s*#\d+)?",
    r"Members?\s+Only[^:]*",
    r"Fan Faves",
    r"Staff Pick",
    r"The Popcorn List",          # "The Popcorn List: The Fisherman" -> "The Fisherman"
]

DEFAULT_STRIP_SUFFIXES = [
    r"\s+w/\s+.*$",                # "Rocky Horror ... w/ ... Shadowcast"
    r":\s+.*\bExperience$",        # "Sleepaway Camp: The Midnight Mass Experience"
    r"\s+Fan First Screenings?$",  # "Supergirl Fan First Screenings"
    r"\s*\(\d{4}\)$",              # trailing release year: "Moana (2026)" -> "Moana"
    r"\s*[-–—]?\s*\d{1,3}(?:st|nd|rd|th)\s+Anniversary$",     # "Citizen Kane 85th Anniversary"
    r"\s*[-–—]\s*Studio Ghibli Fest(?:ival)?(?:\s+\d{4})?$",  # "... - Studio Ghibli Fest 2026"
    r"\s+(?:IMAX\s+)?(?:Opening Night\s+)?Fan Event$",        # "MOANA IMAX Opening Night Fan Event"
    r"\s+(?:IMAX\s+)?(?:Early Access|Advance)\s+Screenings?$",  # "... Early Access Screening"
    r"\s+on\s+\d{2,3}\s?mm$",     # format tag in the title: "Interstellar on 35mm" -> "Interstellar"
]

# Titles matching these are dropped entirely (not a specific movie).
DEFAULT_DROP = [
    r"Screen Unseen",             # AMC mystery screenings
    r"GOLAZO",                    # soccer watch parties
    r"Watch Part(?:y|ies)",
    r"Tokusatsu",                 # recurring series label with no film attached
    r"Private Theatre Rental",    # AMC private-booking options, not public screenings
    r"Copa Mundial",              # FIFA World Cup watch parties (Telemundo), not films
    r"Apple TV Live",             # live sports broadcasts: "F1 on Apple TV Live in IMAX: ..."
    r"Memorial Screening",        # tribute events with no film named: "Classic - ... Memorial Screening"
]


class TitlesCfg(BaseModel):
    # Series/event labels stripped from the START of a film title (see normalize_title).
    strip_prefixes: list[str] = Field(default_factory=lambda: list(DEFAULT_STRIP_PREFIXES))
    # Event descriptors stripped from the END of a film title.
    strip_suffixes: list[str] = Field(default_factory=lambda: list(DEFAULT_STRIP_SUFFIXES))
    # Titles matching any of these are removed (non-film events).
    drop: list[str] = Field(default_factory=lambda: list(DEFAULT_DROP))


class DefaultsCfg(BaseModel):
    # Films pre-checked on first page load (regex, case-insensitive, vs the normalized
    # title). Others start unchecked but available. Empty -> pre-select all films.
    films: list[str] = Field(default_factory=list)


class Config(BaseModel):
    timezone: str = "America/Denver"
    days_ahead: int = 14
    output: str = "public/data.json"
    default_runtime_minutes: int = 120
    theaters: dict[str, TheaterCfg]
    filters: Filters = Field(default_factory=Filters)
    titles: TitlesCfg = Field(default_factory=TitlesCfg)
    defaults: DefaultsCfg = Field(default_factory=DefaultsCfg)


def load_config(path: str | Path = "config.toml") -> Config:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return Config(**data)
