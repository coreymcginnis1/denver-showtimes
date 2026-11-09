"""Shared scraper plumbing: HTTP client, base class, small helpers."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date
from zoneinfo import ZoneInfo

import httpx

from ..config import Config, TheaterCfg
from ..models import Showtime

log = logging.getLogger(__name__)

# Descriptive UA: identify the bot honestly and link to the project.
USER_AGENT = "denver-showtimes-bot/0.1 (+https://coreymcginnis1.github.io/denver-showtimes/; showtimes listing)"


def http_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"},
    )


def to_int(v) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


class BaseScraper(ABC):
    """Each theater adapter returns normalized Showtimes for [start, end] (inclusive)."""

    key: str = ""

    def __init__(self, cfg: Config, theater_cfg: TheaterCfg, key: str | None = None):
        self.cfg = cfg
        self.theater_cfg = theater_cfg
        self.tz = ZoneInfo(cfg.timezone)
        if key:                      # one scraper class can back several theaters (e.g. two AMCs)
            self.key = key

    @abstractmethod
    def fetch(self, start: date, end: date) -> list[Showtime]:
        ...

    # Sources that can look months ahead in a few requests override this (used to find film prints
    # beyond the two-week window). None = not supported.
    def fetch_ahead(self, start: date, end: date) -> list[Showtime] | None:
        return None
