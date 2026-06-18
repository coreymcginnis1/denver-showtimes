"""AMC 9+CO 10 via headless render + DOM parse.

AMC's site is bot-protected (Cloudflare/queue) and JS-rendered, so we render with
Playwright and parse the result. Showtimes are <a href="/showtimes/<id>"> anchors whose
text holds the time and whose aria-describedby ties them to a movie/format heading.
Dates come from a <select name="date"> with value="YYYY-MM-DD" options.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright

from .base import BaseScraper
from ..models import Showtime

log = logging.getLogger(__name__)

SHOWTIMES_URL = "https://www.amctheatres.com/movie-theatres/denver/amc-9-co-10/showtimes"
THEATRE_SLUG = "amc-9-co-10"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([apAP])[mM]")


class AmcScraper(BaseScraper):
    key = "amc"

    def fetch(self, start: date, end: date) -> list[Showtime]:
        results: list[Showtime] = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=UA, locale="en-US", timezone_id=self.cfg.timezone,
                viewport={"width": 1366, "height": 2400},
            )
            page = ctx.new_page()
            try:
                page.goto(SHOWTIMES_URL, wait_until="domcontentloaded", timeout=60000)
                self._wait_showtimes(page)
            except PWTimeout:
                log.warning("amc: showtimes did not render (likely bot-challenged); skipping")
                browser.close()
                return results

            seen_dates: set[date] = set()
            for value, day in self._date_options(page):
                if not (start <= day <= end) or day in seen_dates:
                    continue
                if value:  # "" == Today (already loaded); other dates via ?date=
                    try:
                        page.goto(f"{SHOWTIMES_URL}?date={value}",
                                  wait_until="domcontentloaded", timeout=60000)
                        self._wait_showtimes(page)
                        page.wait_for_timeout(500)
                    except PWTimeout:
                        log.warning("amc: date %s did not load", value)
                        continue
                results.extend(self._parse(page.content(), day))
                seen_dates.add(day)
            browser.close()
        log.info("amc: %d showtimes across %d days", len(results), len(seen_dates))
        return results

    @staticmethod
    def _wait_showtimes(page) -> None:
        page.wait_for_selector('a[href^="/showtimes/"]', timeout=30000)

    def _date_options(self, page) -> list[tuple[str, date]]:
        today = datetime.now(self.tz).date()
        out: list[tuple[str, date]] = []
        try:
            opts = page.eval_on_selector_all(
                'select[name="date"] option', "els => els.map(e => e.value)")
        except Exception:
            opts = []
        for value in opts or [""]:
            if value:
                try:
                    out.append((value, date.fromisoformat(value)))
                except ValueError:
                    continue
            else:
                out.append(("", today))
        return out

    def _parse(self, html: str, day: date) -> list[Showtime]:
        soup = BeautifulSoup(html, "html.parser")
        titles = self._movie_titles(soup)
        results, seen = [], set()
        for a in soup.select('a[href^="/showtimes/"]'):
            href = a.get("href", "")
            m = re.match(r"/showtimes/(\d+)", href)
            if not m or m.group(1) in seen:
                continue
            tm = TIME_RE.search(a.get_text(" ", strip=True))
            if not tm:
                continue
            described = (a.get("aria-describedby") or "").split()
            movie_key = described[0] if described else ""
            mid_match = re.search(r"-(\d+)$", movie_key)
            mid = mid_match.group(1) if mid_match else ""
            title = titles.get(mid) or self._slug_title(movie_key) or "(untitled)"
            hour = int(tm.group(1)) % 12 + (12 if tm.group(3).lower() == "p" else 0)
            start = datetime(day.year, day.month, day.day, hour, int(tm.group(2)), tzinfo=self.tz)
            results.append(Showtime(
                theater=self.key,
                theater_name=self.theater_cfg.name,
                film_title=title,
                start=start,
                fmt=self._format(soup, described),
                ticket_url="https://www.amctheatres.com" + href,
            ))
            seen.add(m.group(1))
        return results

    @staticmethod
    def _movie_titles(soup) -> dict[str, str]:
        """Map AMC movie id -> clean title from the /movies/<slug>-<id> heading links."""
        titles: dict[str, str] = {}
        for a in soup.select('a[href^="/movies/"]'):
            mm = re.search(r"-(\d+)/?$", a.get("href", ""))
            text = a.get_text(" ", strip=True)
            if mm and text and mm.group(1) not in titles:
                titles[mm.group(1)] = text
        return titles

    @staticmethod
    def _slug_title(movie_key: str) -> str | None:
        if not movie_key:
            return None
        return re.sub(r"-\d+$", "", movie_key).replace("-", " ").title() or None

    def _format(self, soup, described: list[str]) -> str | None:
        """Readable format (e.g. 'Dolby Cinema at AMC') from the format-heading element.

        The heading id contains the theatre slug and ends in the experience index
        (e.g. ...-dolbycinemaatamcprime-0); the sibling ...-attributes id is the
        amenities list, which we skip. Text after ' : ' is a marketing tagline.
        """
        for tok in described[1:]:
            if f"-{THEATRE_SLUG}-" not in tok or tok.endswith("-attributes"):
                continue
            if not re.search(r"-\d+$", tok):
                continue
            el = soup.find(id=tok)
            if el and el.get_text(strip=True):
                return el.get_text(" ", strip=True).split(" : ")[0].strip()
        return None
