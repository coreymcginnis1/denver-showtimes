from datetime import datetime
from zoneinfo import ZoneInfo

from movie_scraper.models import Showtime

DEN = ZoneInfo("America/Denver")


def make(**kw):
    base = dict(theater="amc", theater_name="AMC 9+CO 10", film_title="Dune",
                start=datetime(2026, 6, 18, 19, 0, tzinfo=DEN))
    base.update(kw)
    return Showtime(**base)


def test_uid_stable_and_distinct():
    assert make().uid == make().uid
    assert make().uid.startswith("ms_")
    assert make(film_title="Other").uid != make().uid
    assert make(start=datetime(2026, 6, 18, 21, 0, tzinfo=DEN)).uid != make().uid


def test_to_event_timed():
    e = make(end=datetime(2026, 6, 18, 21, 0, tzinfo=DEN), ticket_url="http://x", fmt="Dolby").to_event("#123456")
    assert e["title"] == "Dune"
    assert e["allDay"] is False
    assert e["backgroundColor"] == "#123456"
    assert e["start"].startswith("2026-06-18T19:00")
    assert "end" in e
    assert e["extendedProps"]["ticketUrl"] == "http://x"
    assert e["extendedProps"]["fmt"] == "Dolby"


def test_to_event_all_day_has_no_end():
    e = make(all_day=True).to_event("#000")
    assert e["allDay"] is True
    assert "end" not in e
