"""Regal (UA Colorado Center / Denver Pavilions) via the theatre page's Next.js data.

regmovies.com server-renders the *current day's* full schedule for a theatre into the page's
``__NEXT_DATA__`` (``props.pageProps.showtimes``), which we read with a headless browser.

KNOWN LIMITATION — why this theater ships disabled by default:
The site is behind a **Cloudflare Turnstile "verify you are human"** challenge, and the date
selector loads *future* dates through a client-side call gated by that challenge (the page
route ignores any ``?date=`` param — server-render is always "today"). So a headless run can
reliably get only the server-rendered day, not the rolling window. Enabling Regal for a real
multi-day calendar would need a CAPTCHA/residential approach. The scraper below is correct for
whatever day(s) the page renders, so it's ready if that path is ever solved.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright

from .base import BaseScraper
from ..models import Showtime

log = logging.getLogger(__name__)

THEATRE_URL = "https://www.regmovies.com/theatres/{route}"
DEFAULT_ROUTE = "regal-ua-colorado-center-1308"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
# Generic per-performance tags we don't surface as a "format".
_GENERIC = {"2d", "cc", "dv", "dvs", "ad", "no passes", "stadium", "reserved-selected",
            "reserved", "subtitled", "open caption", "closed caption"}


class RegalScraper(BaseScraper):
    key = "regal"

    def fetch(self, start: date, end: date) -> list[Showtime]:
        route = self.theater_cfg.location or DEFAULT_ROUTE
        url = THEATRE_URL.format(route=route)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                ctx = browser.new_context(user_agent=UA, locale="en-US",
                                          timezone_id=self.cfg.timezone,
                                          viewport={"width": 1366, "height": 2200})
                page = ctx.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_function(
                    "() => window.__NEXT_DATA__ && window.__NEXT_DATA__.props", timeout=30000)
                pp = page.evaluate("() => window.__NEXT_DATA__.props.pageProps") or {}
                browser.close()
        except PWTimeout:
            log.warning("regal %s: page did not render (likely Turnstile-challenged); skipping", route)
            return []

        results = self._parse(pp, route, start, end)
        log.info("regal %s: %d showtimes", route, len(results))
        return results

    def _parse(self, pp: dict, route: str, start: date, end: date) -> list[Showtime]:
        url = THEATRE_URL.format(route=route)
        results: list[Showtime] = []
        for day in pp.get("showtimes") or []:
            for film in day.get("Film") or []:
                title = (film.get("Title") or "").strip()
                if not title:
                    continue
                for perf in film.get("Performances") or []:
                    raw = perf.get("CalendarShowTime")
                    if not raw or perf.get("StopSales"):
                        continue
                    try:
                        dt = datetime.fromisoformat(raw).replace(tzinfo=self.tz)
                    except ValueError:
                        continue
                    if not (start <= dt.date() <= end):
                        continue
                    aud = perf.get("Auditorium")
                    results.append(Showtime(
                        theater=self.key,
                        theater_name=self.theater_cfg.name,
                        film_title=title,
                        start=dt,
                        screen=f"Auditorium {aud}" if aud else None,
                        fmt=self._fmt(perf),
                        ticket_url=url,
                    ))
        return results

    @staticmethod
    def _fmt(perf: dict) -> str | None:
        """Special format from PerformanceGroup/Attributes (IMAX, RPX, 3D, 70MM …)."""
        bits: list[str] = []
        group = (perf.get("PerformanceGroup") or "").strip()
        if group and group.lower() not in _GENERIC | {"2d"}:
            bits.append(group)
        for attr in perf.get("PerformanceAttributes") or []:
            a = (attr or "").strip()
            if a and a.lower() not in _GENERIC and a not in bits:
                bits.append(a)
        return " · ".join(bits) or None
