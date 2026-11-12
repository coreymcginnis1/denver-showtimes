from datetime import date

from movie_scraper.scrapers.alamo import AlamoScraper
from movie_scraper.scrapers.cu_ifs import CuIfsScraper
from movie_scraper.scrapers.dairy import DairyScraper, clean_title
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
    assert any(s.fmt == "IMAX" for s in out)               # named from the amenities, not "Premium Format"
    assert any(s.fmt == "3D" for s in out)                 # RealD 3D is plain 3D
    assert any(s.release_date == "2026-06-26" for s in out)  # release date kept for sorting
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


def test_fandango_skips_its_placeholder_poster():
    """Fandango returns its grey "F" image when it has no art; never keep that as a poster."""
    base = "https://images.fandango.com/ImageRenderer/300/0/redesign/static/img/default_poster.png/0/"
    none = {"poster": {"size": {"300": base + "images.fandango.com/redesign/static/img/default_poster.png"}}}
    real = {"poster": {"size": {"300": base + "images/MasterRepository/fandango/1/poster.jpg"}}}
    assert FandangoScraper._poster(none) is None
    assert FandangoScraper._poster(real).startswith("https://images.fandango.com/ImageRenderer/600/")


def test_fandango_names_premium_screens():
    """IMAX and Dolby are named; branded premium screens are just "PLF"; 3D keeps IMAX/Dolby."""
    f = FandangoScraper._fmt
    prem, three_d = {"filmFormatHeader": "Premium Format"}, {"filmFormatHeader": "3D"}
    group = lambda *names: {"amenities": [{"name": n} for n in names]}
    assert f(prem, group("Dolby Cinema @ AMC", "Reserved seating")) == "Dolby"
    assert f(prem, group("IMAX with Laser", "IMAX")) == "IMAX"
    assert f(prem, group("PRIME at AMC")) == "PLF"
    assert f(prem, group("CINÉ XL®")) == "PLF"
    assert f(prem, group("RPX", "Recliner Seats")) == "PLF"
    assert f(three_d, group("4DX", "RealD 3D")) == "3D"
    assert f(three_d, group("IMAX", "RealD 3D")) == "IMAX 3D"
    assert f(prem, group("IMAX 70MM")) == "IMAX 70mm"
    assert f(prem, group("Reserved seating")) == "PLF"                 # unnamed premium screen
    assert f({"filmFormatHeader": "Standard"}, group("Laser at AMC", "Dolby Atmos")) is None


def test_languages():
    from movie_scraper.formats import language
    assert language(["Japanese with English Subtitles", "Reserved seating"]) == "Subtitled"
    assert language(["English Subtitles", "Hindi Language"]) == "Subtitled"
    assert language(["Spanish Dubbed"]) == "Spanish dub"
    assert language(["English Dubbed"]) == "Dubbed"
    assert language(["Reserved seating", "Hindi Language"]) == "Hindi language"   # page decides sub vs dub
    assert language(["Japanese Language", "CINÉ XL®"]) == "Japanese language"
    assert language(["English Language"]) is None
    assert language(["Laser at AMC"]) is None


def test_landmark_hides_aspect_ratio_formats():
    assert LandmarkScraper._fmt(["Format.Projection.Scope"]) is None
    assert LandmarkScraper._fmt(["Format.Projection.Digital"]) is None
    assert LandmarkScraper._fmt(["Format.Projection.35mm"]) == "35mm"
    assert LandmarkScraper._fmt(["Format.Projection.70mm"]) == "70mm"


def test_landmark_reads_its_subtitled_tag():
    lang = LandmarkScraper._lang
    assert lang(["Screen.Accessibility.HearingImpaired", "Showtime.Accessibility.Subtitled"]) == "Subtitled"
    assert lang(["Showtime.Accessibility.ClosedCaption", "Format.Projection.Digital"]) is None


def test_sie_subtitles_and_print_tags():
    from movie_scraper.scrapers.sie_eventive import SieScraper
    lang = SieScraper._lang
    assert lang({"language": "Spanish", "subtitle_language": "English"}) == "Subtitled"
    assert lang({"language": "German, English", "subtitle_language": "English"}) == "Subtitled"
    assert lang({"language": "English", "subtitle_language": "English"}) is None    # captions, not a sub
    assert lang({"language": "Japanese"}) is None                                    # no subtitle track listed


def test_dairy_build(cfg, dairy_events):
    scraper = DairyScraper(cfg, cfg.theaters["dairy"], key="dairy")
    out = scraper.build(dairy_events["events"], date(2026, 11, 1), date(2027, 2, 7))
    titles = {s.film_title for s in out}
    assert "Queen at Sea" in titles and "The History of Concrete" in titles   # run dates stripped
    assert "Nova '78" in titles                                                # "| Dec 29 – Jan 3"
    assert not any("Cinema Club" in t or "Youth Advisory" in t for t in titles)   # talks, meetings
    assert all(s.theater == "dairy" and s.start.tzinfo is not None and not s.all_day for s in out)
    assert all((s.ticket_url or "").startswith("https://thedairy.org/event/") for s in out)
    queen = next(s for s in out if s.film_title == "Queen at Sea")
    assert queen.screen == "Boedecker Theater" and queen.start.hour == 14 and queen.end > queen.start
    assert queen.poster and queen.poster.startswith("https://")
    assert next(s for s in out if s.film_title.startswith("Friday Night Weird")).screen is None   # just "Dairy Arts Center"
    # outside the window: nothing
    assert scraper.build(dairy_events["events"], date(2025, 1, 1), date(2025, 1, 2)) == []


def test_dairy_clean_title():
    assert clean_title("Queen at Sea | Nov. 11 &#8211; 14") == "Queen at Sea"
    assert clean_title("Once Upon a Time in Harlem | Nov. 25-29") == "Once Upon a Time in Harlem"
    assert clean_title("Nova ’78 | Dec 29 – Jan 3") == "Nova '78"
    assert clean_title("The History of Concrete November 19 – 23") == "The History of Concrete"
    assert clean_title("Fjord | Nov. 19") == "Fjord"
    assert clean_title("Ocean's Eleven") == "Ocean's Eleven"   # nothing to strip
    assert clean_title("Mountains on Stage – Winter Edition 2026") == "Mountains on Stage – Winter Edition 2026"


def test_cu_ifs_build(cfg, cu_ifs_events):
    scraper = CuIfsScraper(cfg, cfg.theaters["cu_ifs"], key="cu_ifs")
    out = scraper.build([x["event"] for x in cu_ifs_events["events"]], date(2026, 8, 15), date(2027, 2, 7))
    titles = {s.film_title for s in out}
    assert "IFS Volunteer Orientation" not in titles          # not a film
    assert {"Them! on 35mm", "King Kong (1933)", "The Big Lebowski"} <= titles   # pipeline rules clean them later
    kong = next(s for s in out if s.film_title == "King Kong (1933)")
    assert kong.year == 1933                                    # the stated year guides the TMDB match
    them = next(s for s in out if s.film_title == "Them! on 35mm")
    assert them.screen == "Muenzinger Auditorium" and them.start.hour == 19 and them.start.minute == 30
    assert them.ticket_url.startswith("https://www.internationalfilmseries.com/")
    assert all(s.theater == "cu_ifs" and str(s.start.tzinfo) == "America/Denver" for s in out)


def test_thirty_mile_theaters_configured(cfg):
    for key, scraper in [("dairy", "dairy"), ("cu_ifs", "cu_ifs"), ("amc_orchard", "fandango"), ("amc_flatiron", "fandango"),
                         ("amc_southlands", "fandango"), ("emagine_parker", "fandango"), ("amc_brighton", "fandango"),
                         ("amc_castle_rock", "fandango"), ("cinemark_boulder", "fandango"), ("regal_longmont", "fandango")]:
        t = cfg.theaters[key]
        assert t.enabled and t.default_on is False and t.scraper == scraper and t.lat and t.lon
