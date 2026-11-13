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
    location: Optional[str] = None   # scraper-specific id (Alamo venue / Fandango theater id)
    lat: Optional[float] = None      # where the theater is, for the site's distance-from-zip filter
    lon: Optional[float] = None
    site: Optional[str] = None       # the theater's own page, for "Or buy from AMC directly" (Fandango theaters)


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
    r"Scream Screen",             # Sie horror series: "Scream Screen: Idle Hands" -> "Idle Hands"
    r"Fan Faves",
    r"Staff Pick",
    r"The Popcorn List",          # "The Popcorn List: The Fisherman" -> "The Fisherman"
    r"Crunchyroll(?:\s+Anime\s+Nights?)?",   # "Crunchyroll Anime Nights: Dive In Wonderland"
    r"(?:\w+\s+)?Dose of Reality(?:\s+Screening)?",  # Sie doc series: "Big Dose of Reality Screening: X"
    r"[^:]{2,40}?\s+Presents",    # presenter labels: "Sight & Sound Presents: Joshua Live!"
    r"Friday Night Weird",        # Dairy series: "Friday Night Weird: These People" -> "These People"
    r"Cinema Classics(?:\s+with\s+[^:]{2,40}?)?",   # Dairy: "Cinema Classics with Jeffrey Kash: Modern Times"
    r"Film Screening",            # CU calendar: "Film Screening: Little Amélie or the Character of Rain"
]

DEFAULT_STRIP_SUFFIXES = [
    r"\s+w/\s+.*$",                # "Rocky Horror ... w/ ... Shadowcast"
    r"\s*[-–—:]?\s*\(?(?:New\s+)?[248]K\s+(?:Restoration|Restored|Remaster(?:ed)?)\)?$",   # "The Host 4K Restoration" / "(4K Restoration)"
    r"\s*\((?:Newly\s+)?(?:Restored|Restoration|Remastered)\)$",   # "Suspiria (Restored)"
    r"\s+[-–—]\s+[^-–—]*\bin person!?$",     # guests: "Elevation - Anthony Mackie and George Nolfi in person!"
    r"\s+[-–—]\s+Part of\s.+$",              # festivals: "Breathless - Part of the Albertine ... Festival"
    r"\s+[-–—]\s+Free\s+(?:Show|Screening)$",   # "Whiplash - FREE SHOW"
    r"\s+[-–—]\s+IFS Underground$",          # CU IFS late-night series: "Café Flesh - IFS Underground"
    r":\s+.*\bExperience$",        # "Sleepaway Camp: The Midnight Mass Experience"
    r"\s+Fan First Screenings?$",  # "Supergirl Fan First Screenings"
    r"\s*\(\d{4}\)$",              # trailing release year: "Moana (2026)" -> "Moana"
    r"\s*[-–—:]?\s*\(?\d{1,3}(?:st|nd|rd|th)\s+Anniversary\)?$",  # "85th Anniversary" / ": 10th Anniversary"
    r"\s*[-–—:]?\s*\(?(?:Director\W?s|Extended|Theatrical|Final|Uncut)\s+Cut\)?$",  # "- Directors Cut" -> base film
    r"\s*[:–—-]\s*[^:]*\bEdition$",   # "Backrooms: Everything Must Go Edition" -> "Backrooms"
    r"\s*[-–—]\s*(?:Promo|Preview|Sneak(?:\s+Preview)?)\s+Screenings?$",   # "... - Promo Screening"
    r"\s*[-–—]\s*Studio Ghibli Fest(?:ival)?(?:\s+\d{4})?$",  # "... - Studio Ghibli Fest 2026"
    r"\s+(?:IMAX\s+)?(?:Opening Night\s+)?Fan Event$",        # "MOANA IMAX Opening Night Fan Event"
    r"\s+(?:IMAX\s+)?(?:Early Access(?:\s+Screenings?)?|Advance\s+Screenings?)$",  # "... Early Access [Screening]"
    r"\s*[-–—:]\s*Super Ticket$",                          # ticket bundles: "The Hunger Games: ... - Super Ticket"
    r"\s*[-–—:]?\s*\(?\b(?:Re-?release|Re-?issue|RE\d{2})\)?$",  # "Coraline Re-release" / "Dune: Part One Reissue" / "(RE26)"
    r"\s+(?:on|in)\s+(?:\d{2,3}\s?mm|VistaVision)(?:\s+film)?$",   # "Interstellar on 35mm" / "... in 70mm" / "... in VistaVision"
    r"\s*[:–—-]\s*Sensory[- ]?Friendly\b.*$",  # "Supergirl: Sensory Friendly Screening" -> "Supergirl"
    r"\s*\(dir\.?\s[^)]*\)$",     # director annotation: "Alpha (dir. Rawail)" -> "Alpha"
    r"\s*[:–—-]\s*Xfinity\b.*$",  # sponsor tag: "Minions & Monsters: Xfinity" -> "Minions & Monsters"
    r"\s*[-–—:]?\s+Encore$",      # rebroadcasts: "The Metropolitan Opera: Carmen Encore" -> "... Carmen"
    r"\s*\((?:\d{4}\s+)?Encore\)$",  # "... Carmen (2026 Encore)" -> "... Carmen"
    r"\s*\((?:English|Spanish|Hindi|Telugu|Tamil|Malayalam|Kannada|Punjabi|Japanese|Korean)(?:\s+(?:\d{4}|Dub(?:bed)?|Sub(?:titled)?|Version))?\)$",  # language versions: "Ramayana (English 2026)"
    r"\s*\((?:Subtitled|Dubbed)\)$",  # "Tokyo Godfathers (Subtitled)": the tag becomes the showing's language
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
    r"Mystery Movie",
    r"^IFS Underground$",         # CU IFS late-night series with no film named
    r"Secret (?:Cinema|Movie)",   # mystery screenings, no film named (Harkins Secret Cinema, Cinemark Secret Movie Series)
    r"\bUFC \d",                  # live UFC pay-per-view broadcasts ("UFC 329: ..."), not films
    r"Members?\s+Only",           # members-only screenings (public can't attend) — drop them
    r"League of Legends",         # live esports broadcasts ("League of Legends Worlds 26 - Finals")
    r"\bE-?sports?\b",
]


class TitlesCfg(BaseModel):
    # Series/event labels stripped from the START of a film title (see normalize_title).
    strip_prefixes: list[str] = Field(default_factory=lambda: list(DEFAULT_STRIP_PREFIXES))
    # Event descriptors stripped from the END of a film title.
    strip_suffixes: list[str] = Field(default_factory=lambda: list(DEFAULT_STRIP_SUFFIXES))
    # Titles matching any of these are removed (non-film events).
    drop: list[str] = Field(default_factory=lambda: list(DEFAULT_DROP))


class TmdbCfg(BaseModel):
    # Look films up on TMDB for release dates, popularity and ratings (needs TMDB_TOKEN).
    enabled: bool = True
    # Normalized title -> TMDB movie id, for the few titles the automatic match gets wrong.
    overrides: dict[str, int] = Field(default_factory=dict)
    # Film title as the site shows it -> its languages (ISO 639-1 codes) in the order the page lists
    # them, where the automatic one is wrong or incomplete: Fjord = ["en", "ro", "no"].
    languages: dict[str, list[str]] = Field(default_factory=dict)


class OmdbCfg(BaseModel):
    # Metacritic scores via OMDb (needs OMDB_API_KEY). Off since Nov 2026: OMDb leaves most
    # current releases unscored for weeks, so ratings were dropped from the site (see CLAUDE.md).
    enabled: bool = False


class TrendingCfg(BaseModel):
    # Blend 7-day English Wikipedia page views into "Trending" (50/50 with TMDB popularity ranks).
    wikipedia: bool = True


class CriticsCfg(BaseModel):
    # Each film's Metacritic score as its English Wikipedia article reports it, shown in the
    # film page only (no sort). Metacritic itself has no free API and forbids scraping.
    metacritic: bool = True


class Config(BaseModel):
    timezone: str = "America/Denver"
    days_ahead: int = 14
    # Theaters whose source can look far ahead in a request or a few (Sie, Landmark, Alamo) report
    # everything up to this many days out; the chains (Fandango, one request a day) stop at days_ahead.
    ahead_days: int = 90
    output: str = "public/data.json"
    theaters: dict[str, TheaterCfg]
    filters: Filters = Field(default_factory=Filters)
    titles: TitlesCfg = Field(default_factory=TitlesCfg)
    tmdb: TmdbCfg = Field(default_factory=TmdbCfg)
    omdb: OmdbCfg = Field(default_factory=OmdbCfg)
    critics: CriticsCfg = Field(default_factory=CriticsCfg)
    trending: TrendingCfg = Field(default_factory=TrendingCfg)


def load_config(path: str | Path = "config.toml") -> Config:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return Config(**data)
