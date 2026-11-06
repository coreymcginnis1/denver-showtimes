from datetime import date

from movie_scraper.scrapers.alamo import AlamoScraper
from movie_scraper.scrapers.fandango import FandangoScraper
from movie_scraper.scrapers.landmark import LandmarkScraper
from movie_scraper.scrapers.sie_eventive import SieScraper


def test_sie_build(cfg, sie_payload):
    films = {f["id"]: f for f in sie_payload["films"]}
    scraper = SieScraper(cfg, cfg.theaters["sie"])
    out = scraper.build(films, sie_payload["shows_by_day"], date(2026, 6, 18), date(2026, 7, 2))

    assert out, "expected Sie showtimes from fixture"
    assert all(s.theater == "sie" and not s.all_day for s in out)
    assert all(s.start.tzinfo is not None for s in out)
    assert all("denverfilm.eventive.org/films/" in (s.ticket_url or "") for s in out)
    assert any("Bleak Week" in s.film_title for s in out)


def test_landmark_build(cfg, landmark_schedule, landmark_movies):
    sched = landmark_schedule["X02AK"]["schedule"]
    raw = {}
    for mid, by_date in sched.items():
        for shows in by_date.values():
            raw.setdefault(mid, []).extend(shows)
    movies = {str(m["id"]): m for m in landmark_movies}
    scraper = LandmarkScraper(cfg, cfg.theaters["landmark"])
    out = scraper.build(raw, movies, date(2026, 6, 18), date(2026, 6, 30))

    assert out, "expected Landmark showtimes from fixture"
    assert all(s.theater == "landmark" and not s.all_day for s in out)   # now timed, not days-only
    assert all(s.start.tzinfo is not None for s in out)
    assert any(s.screen for s in out)                                     # screen/auditorium names
    assert any(s.screen and ("Downstairs" in s.screen or "Upstairs" in s.screen) for s in out)
    assert all("landmarktheatres.com" in (s.ticket_url or "") for s in out)
    assert any(not s.film_title.startswith("Movie ") for s in out)       # titles resolved


def test_alamo_build(cfg, alamo_schedule):
    scraper = AlamoScraper(cfg, cfg.theaters["alamo_sloans"], key="alamo_sloans")
    out = scraper.build(alamo_schedule["data"], "sloans-lake", date(2026, 6, 29), date(2026, 6, 30))

    assert out, "expected Alamo showtimes from fixture"
    assert all(s.theater == "alamo_sloans" and not s.all_day for s in out)
    assert all(s.start.tzinfo is not None for s in out)
    assert any(s.screen and s.screen.startswith("Screen ") for s in out)
    assert all("drafthouse.com/" in (s.ticket_url or "") for s in out)
    assert any(s.film_title and s.film_title != "(untitled)" for s in out)
    assert all(len(s.film_title) < 90 for s in out)        # real titles, not blobs


def test_fandango_parse(cfg, fandango_showtimes):
    scraper = FandangoScraper(cfg, cfg.theaters["regal_colorado"], key="regal_colorado")
    out = scraper.parse_day(fandango_showtimes["viewModel"], date(2026, 6, 29), date(2026, 6, 29))

    assert out, "expected Fandango showtimes from fixture"
    assert all(s.theater == "regal_colorado" and not s.all_day for s in out)
    assert all(s.start.tzinfo is not None and s.start.date() == date(2026, 6, 29) for s in out)
    assert all("fandango.com" in (s.ticket_url or "") for s in out)
    assert any("Supergirl" in s.film_title for s in out)
    assert any(s.fmt == "Premium Format" for s in out)     # surfaced; "Standard" is hidden
    assert all(s.fmt != "Standard" for s in out)


def test_fandango_backs_amc_theaters(cfg, fandango_showtimes):
    """The AMC theaters read from Fandango and keep their own keys and ids."""
    assert cfg.theaters["amc"].location == "AAYUA"
    assert cfg.theaters["amc_westminster"].location == "AAECN"

    west = FandangoScraper(cfg, cfg.theaters["amc_westminster"], key="amc_westminster")
    out = west.parse_day(fandango_showtimes["viewModel"], date(2026, 6, 29), date(2026, 6, 29))
    assert out
    assert all(s.theater == "amc_westminster" for s in out)   # tagged as their own theater
    assert all(s.theater_name == "AMC Westminster Promenade 24" for s in out)
