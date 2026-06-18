"""Load and validate config.toml."""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class TheaterCfg(BaseModel):
    enabled: bool = True
    name: str
    color: str = "#888888"


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
]

DEFAULT_STRIP_SUFFIXES = [
    r"\s+w/\s+.*$",                # "Rocky Horror ... w/ ... Shadowcast"
    r":\s+.*\bExperience$",        # "Sleepaway Camp: The Midnight Mass Experience"
    r"\s+Fan First Screenings?$",  # "Supergirl Fan First Screenings"
]

# Titles matching these are dropped entirely (not a specific movie).
DEFAULT_DROP = [
    r"Screen Unseen",             # AMC mystery screenings
    r"GOLAZO",                    # soccer watch parties
    r"Watch Part(?:y|ies)",
    r"Tokusatsu",                 # recurring series label with no film attached
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
