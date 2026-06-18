from datetime import date

from movie_scraper.scrapers.amc import AmcScraper
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


def test_landmark_build(cfg, landmark_scheduled, landmark_movies):
    scheduled = landmark_scheduled["scheduledDays"]
    movies = {str(m["id"]): m for m in landmark_movies}
    scraper = LandmarkScraper(cfg, cfg.theaters["landmark"])
    out = scraper.build(scheduled, movies, date(2026, 6, 1), date(2026, 12, 31))

    assert out, "expected Landmark day-entries from fixture"
    assert all(s.theater == "landmark" and s.all_day for s in out)
    assert all("landmarktheatres.com/movies/" in (s.ticket_url or "") for s in out)
    assert any(not s.film_title.startswith("Movie ") for s in out)  # titles resolved from movies
    assert any("Lebowski" in s.film_title for s in out)


def test_amc_parse(cfg, amc_html):
    scraper = AmcScraper(cfg, cfg.theaters["amc"])
    out = scraper._parse(amc_html, date(2026, 6, 18))

    assert len(out) > 20
    titles = {s.film_title for s in out}
    assert "Toy Story 5" in titles
    assert "Backrooms" in titles
    assert all(s.theater == "amc" and not s.all_day for s in out)
    assert all("amctheatres.com/showtimes/" in (s.ticket_url or "") for s in out)
    # titles must be the clean film name, not the whole movie-card text dump
    assert all(len(s.film_title) < 80 for s in out)
    assert all("AMC Signature" not in s.film_title for s in out)
    assert any(s.fmt for s in out)  # at least some formats parsed (Dolby/Laser/RealD)
