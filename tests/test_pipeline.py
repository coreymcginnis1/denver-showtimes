import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from movie_scraper import cli, pipeline
from movie_scraper.config import (
    DEFAULT_DROP, DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES, load_config,
)
from movie_scraper.models import Showtime
from movie_scraper.pipeline import (
    _build_feed, _passes, diff_new_titles, is_non_film, normalize_title, render_summary, run,
    title_format, title_lang,
)

DEN = ZoneInfo("America/Denver")
ROOT = Path(__file__).parent.parent


def fresh_cfg():
    return load_config(ROOT / "config.toml")


def st(title="Dune", hour=19, theater="amc", all_day=False):
    return Showtime(theater=theater, theater_name="T", film_title=title,
                    start=datetime(2026, 6, 19, hour, 0, tzinfo=DEN), all_day=all_day)


def test_filter_title_include():
    c = fresh_cfg()
    c.filters.title_include = ["dune"]
    assert _passes(st("Dune: Part Two"), c)
    assert not _passes(st("Barbie"), c)


def test_filter_weekday():
    c = fresh_cfg()
    c.filters.weekdays = ["Fri"]            # 2026-06-19 is a Friday
    assert _passes(st(), c)
    c.filters.weekdays = ["Mon"]
    assert not _passes(st(), c)


def test_filter_time_window():
    c = fresh_cfg()
    c.filters.earliest = "17:00"
    assert _passes(st(hour=19), c)
    assert not _passes(st(hour=12), c)
    # all-day entries are not excluded by a time window
    assert _passes(st(hour=0, all_day=True), c)


def test_normalize_title_strips_series():
    P = DEFAULT_STRIP_PREFIXES
    assert normalize_title("Bleak Week: The Sweet Hereafter", P) == "The Sweet Hereafter"
    assert normalize_title("Sie/Saw: eXistenZ", P) == "eXistenZ"
    assert normalize_title("Sci-Fi Film Series #1: Jaws", P) == "Jaws"
    assert normalize_title("Fan Faves: Michael", P) == "Michael"


def test_normalize_title_preserves_real_colons():
    P = DEFAULT_STRIP_PREFIXES
    assert normalize_title("Star Wars: The Mandalorian and Grogu", P) == "Star Wars: The Mandalorian and Grogu"
    assert normalize_title("The Amazing Digital Circus: The Last Act", P) == "The Amazing Digital Circus: The Last Act"
    assert normalize_title("Toy Story 5", P) == "Toy Story 5"


def test_normalize_title_strips_suffix_and_caps():
    P, S = DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES
    assert normalize_title("Rocky Horror Picture Show w/ CO's Elusive Ingredient Shadowcast", P, S) == "Rocky Horror Picture Show"
    assert normalize_title("Sleepaway Camp: The Midnight Mass Experience", P, S) == "Sleepaway Camp"
    assert normalize_title("Supergirl Fan First Screenings", P, S) == "Supergirl"
    assert normalize_title("STOP! THAT! TRAIN!", P, S) == "Stop! That! Train!"


def test_normalize_title_strips_year_and_event_suffixes():
    P, S = DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES
    assert normalize_title("Moana (2026)", P, S) == "Moana"
    assert normalize_title("Scarface (1983)", P, S) == "Scarface"
    assert normalize_title("Citizen Kane 85th Anniversary", P, S) == "Citizen Kane"
    assert normalize_title("Talladega Nights: Ballad of Ricky Bobby - 20th Anniversary", P, S) == "Talladega Nights: Ballad of Ricky Bobby"
    assert normalize_title("My Neighbor Totoro - Studio Ghibli Fest 2026", P, S) == "My Neighbor Totoro"
    assert normalize_title("MOANA IMAX Opening Night Fan Event", P, S) == "Moana"
    assert normalize_title("Minions & Monsters Early Access Screening", P, S) == "Minions & Monsters"
    # a real number in parens that isn't a 4-digit year is left alone
    assert normalize_title("Se7en", P, S) == "Se7en"


def test_normalize_title_lowercase_to_titlecase():
    assert normalize_title("jackass: best and last") == "Jackass: Best and Last"
    assert normalize_title("the lord of the rings") == "The Lord of the Rings"
    # mixed-case titles are left untouched (only uniform upper/lower get re-cased)
    assert normalize_title("To Wong Foo, Thanks for Everything, Julie Newmar") == "To Wong Foo, Thanks for Everything, Julie Newmar"


def test_is_non_film_drops_soccer_watch_parties():
    assert is_non_film("Argentina vs Cabo Verde - Telemundo presenta la Copa Mundial de la FIFA 2026", DEFAULT_DROP)
    assert is_non_film("Cuartos de Final - Telemundo presenta la Copa Mundial de la FIFA 2026", DEFAULT_DROP)
    assert not is_non_film("Supergirl", DEFAULT_DROP)


def test_normalize_title_series_prefix_and_format_suffix():
    P, S = DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES
    assert normalize_title("The Popcorn List: The Fisherman", P) == "The Fisherman"
    assert normalize_title("Interstellar on 35mm", P, S) == "Interstellar"
    assert normalize_title("Oppenheimer on 70mm", P, S) == "Oppenheimer"
    assert normalize_title("Minions & Monsters: Xfinity", P, S) == "Minions & Monsters"
    # a real colon subtitle that isn't a sponsor tag is preserved
    assert normalize_title("Mission: Impossible", P, S) == "Mission: Impossible"


def test_normalize_title_consolidates_editions_cuts_anniversaries():
    P, S = DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES
    assert normalize_title("Backrooms: Everything Must Go Edition", P, S) == "Backrooms"
    assert normalize_title("Alien - Director's Cut", P, S) == "Alien"
    assert normalize_title("Blade Runner - Final Cut", P, S) == "Blade Runner"
    # both a cut and a parenthetical anniversary strip off
    assert normalize_title("Aliens: Director's Cut (40th Anniversary)", P, S) == "Aliens"
    assert normalize_title("Jaws (45th Anniversary)", P, S) == "Jaws"


def test_normalize_title_strips_series_and_screening_labels():
    P, S = DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES
    assert normalize_title("Scream Screen: Idle Hands", P, S) == "Idle Hands"
    assert normalize_title("Supergirl: Sensory Friendly Screening", P, S) == "Supergirl"
    assert normalize_title("The Odyssey on 35mm film", P, S) == "The Odyssey"
    assert normalize_title("Alpha (dir. Rawail)", P, S) == "Alpha"
    assert normalize_title("Interstellar on 35mm", P, S) == "Interstellar"   # plain form still works


def test_is_non_film_drops_members_only():
    assert is_non_film("Some Indie Film - Promo Screening (Members Only)", DEFAULT_DROP)
    assert is_non_film("Member Only Sneak Preview: The Invite", DEFAULT_DROP)
    assert not is_non_film("The Invite", DEFAULT_DROP)


def test_diff_new_titles(tmp_path):
    kp = tmp_path / "known.txt"
    assert diff_new_titles(["Jaws", "Alien"], kp) == ["Alien", "Jaws"]   # first run: all new
    assert kp.exists()
    assert diff_new_titles(["Jaws", "Alien", "Dune"], kp) == ["Dune"]    # only the genuinely new one
    assert diff_new_titles(["Jaws"], kp) == []                           # nothing new (fewer is fine)


def test_is_non_film_drops_live_broadcast_and_memorial():
    assert is_non_film("F1 on Apple TV Live in IMAX: British Race", DEFAULT_DROP)
    assert is_non_film("Classic - Tim Kaminski Memorial Screening", DEFAULT_DROP)
    assert not is_non_film("F1", DEFAULT_DROP)            # the real 2025 film must survive
    assert not is_non_film("F1: The Movie", DEFAULT_DROP)


def test_title_format_extraction_vistavision_and_in():
    assert title_format("One Battle After Another in VistaVision") == "VistaVision"
    assert title_format("Lawrence of Arabia in 70mm") == "70mm"
    assert normalize_title("Lawrence of Arabia in 70mm", DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES) == "Lawrence of Arabia"


def test_title_format_extraction():
    assert title_format("Interstellar on 35mm") == "35mm"
    assert title_format("Oppenheimer on 70mm") == "70mm"
    assert title_format("Interstellar") is None


def test_title_lang_and_bare_language_tags():
    assert title_lang("Tokyo Godfathers (Subtitled)") == "Subtitled"
    assert title_lang("Tokyo Godfathers (Dubbed)") == "Dubbed"
    assert title_lang("Pushpa 2 (Hindi Dubbed)") == "Hindi dub"
    assert title_lang("Ramayana (English 2026)") is None
    assert title_lang("Tokyo Godfathers") is None
    for t in ("Tokyo Godfathers (Subtitled)", "Tokyo Godfathers (Dubbed)"):
        assert normalize_title(t, DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES) == "Tokyo Godfathers"


def test_rocky_horror_override():
    assert fresh_cfg().tmdb.overrides["Rocky Horror Picture Show"] == 36685


def test_normalize_title_recases_allcaps_words():
    P = DEFAULT_STRIP_PREFIXES
    # 4+ letter all-caps words in a mixed-case title are down-cased so variants merge
    assert normalize_title("BLEACH: Thousand-Year Blood War - The Calamity", P) == \
        "Bleach: Thousand-Year Blood War - The Calamity"
    assert normalize_title("The LEGO Ninjago Movie", P) == "The Lego Ninjago Movie"
    assert normalize_title("Jack Johnson: SURFILMUSIC", P) == "Jack Johnson: Surfilmusic"
    # short interior acronyms are left alone
    assert normalize_title("UFC 329: McGregor vs. Holloway 2", P) == "UFC 329: McGregor vs. Holloway 2"
    # all-caps connector words are lowered mid-title, capitalized where a phrase starts
    assert normalize_title("Terror IN THE Aisles II (12-Hour Horror Marathon)", P) == \
        "Terror in the Aisles II (12-Hour Horror Marathon)"
    assert normalize_title("Halloween: THE Night He Came Home", P) == "Halloween: The Night He Came Home"
    assert normalize_title("Plan A", P) == "Plan A"                       # single letters stay
    assert normalize_title("Star Wars: Episode IV - A New Hope", P) == "Star Wars: Episode IV - A New Hope"


def test_restorations_are_stripped_and_lose_the_rerelease_year():
    P, S = DEFAULT_STRIP_PREFIXES, DEFAULT_STRIP_SUFFIXES
    for raw, want in [("The Host 4K Restoration", "The Host"), ("Paris, Texas (4K Restoration)", "Paris, Texas"),
                      ("Possession - New 4K Remaster", "Possession"), ("Suspiria (Restored)", "Suspiria"),
                      ("Paris, Texas (1984) 4K Restoration", "Paris, Texas"),
                      ("The Host 4K Restoration (2026)", "The Host")]:     # Fandango's actual title
        assert normalize_title(raw, P, S) == want
        assert pipeline.revival_tagged(raw, want)          # Fandango's date is the re-release's
    assert normalize_title("Restoration", P, S) == "Restoration"   # a film called that is kept
    assert pipeline.revival_tagged("Coraline Re-release", "Coraline")
    assert not pipeline.revival_tagged("Restoration", "Restoration")
    assert not pipeline.revival_tagged("The Host", "The Host")


def test_is_non_film_drops_ufc_broadcasts():
    assert is_non_film("UFC 329: McGregor vs. Holloway 2", DEFAULT_DROP)
    assert not is_non_film("Jack Johnson: Surfilmusic", DEFAULT_DROP)


def test_is_non_film_drops_mystery_series():
    assert is_non_film("Harkins Secret Cinema", DEFAULT_DROP)
    assert is_non_film("Cinemark Secret Movie Series", DEFAULT_DROP)
    assert is_non_film("IFS Underground", DEFAULT_DROP)        # a series night with no film named
    assert not is_non_film("Café Flesh", DEFAULT_DROP)
    assert not is_non_film("The Secret Agent", DEFAULT_DROP)


def test_is_non_film_drop():
    assert is_non_film("AMC Screen Unseen: June 22", DEFAULT_DROP)
    assert is_non_film("¡GOLAZO!: 2026 Soccer Watch Parties", DEFAULT_DROP)
    assert is_non_film("Tokusatsu Tuesdsay", DEFAULT_DROP)
    assert not is_non_film("Jaws", DEFAULT_DROP)
    assert not is_non_film("The Big Lebowski", DEFAULT_DROP)


def test_build_feed_shape():
    c = fresh_cfg()
    feed = _build_feed(c, [st("A", 19, "amc"), st("B", 20, "sie")], DEN)
    assert {"generated_at", "timezone", "theaters", "films", "events"} <= set(feed)
    assert feed["films"] == ["A", "B"]
    assert len(feed["events"]) == 2
    assert {e["extendedProps"]["theater"] for e in feed["events"]} == {"amc", "sie"}


def test_secondary_theaters_config():
    c = fresh_cfg()
    assert c.theaters["sie"].default_on is True             # primary theaters start on
    assert c.theaters["amc"].default_on is False
    assert c.theaters["amc_westminster"].default_on is False  # secondary start off
    assert c.theaters["amc"].scraper == "fandango"          # AMC reads from Fandango
    assert c.theaters["amc_westminster"].scraper == "fandango"
    assert c.theaters["alamo_sloans"].default_on is False
    for key, loc in (("alamo_westminster", "westminster"), ("alamo_littleton", "littleton")):
        t = c.theaters[key]                                   # same Alamo feed, its own location
        assert t.enabled and t.default_on is False and t.scraper == "alamo" and t.location == loc
        assert t.lat and t.lon                                # for the distance filter
    assert c.theaters["regal_colorado"].enabled is True     # scraped via Fandango
    assert c.theaters["regal_colorado"].default_on is False  # but off by default
    assert c.theaters["regal_colorado"].scraper == "fandango"


def test_build_feed_lists_each_poster_once_per_film():
    a1, a2, b = st("A", 19, "amc"), st("A", 21, "regal_pavilions"), st("B", 20, "amc")
    a1.poster = a2.poster = "https://img/a.jpg"
    b.poster = "https://img/a.jpg"                 # same art on another film still shows for it
    feed = _build_feed(fresh_cfg(), [a2, b, a1], DEN)
    got = [(e["title"], e["start"][11:16], e["extendedProps"].get("poster")) for e in feed["events"]]
    assert got == [("A", "19:00", "https://img/a.jpg"), ("B", "20:00", "https://img/a.jpg"), ("A", "21:00", None)]


def test_carried_rows_get_their_poster_back():
    prev = {"events": [
        {"title": "A", "start": "2026-06-18T19:00:00-06:00", "extendedProps": {"theater": "flaky", "poster": "p.jpg"}},
        {"title": "A", "start": "2026-06-20T19:00:00-06:00", "extendedProps": {"theater": "flaky"}},
        {"title": "B", "start": "2026-06-20T19:00:00-06:00", "extendedProps": {"theater": "flaky"}},
    ]}
    out = pipeline._carried_events(prev, ["flaky"], date(2026, 6, 19))
    assert [(e["title"], e["extendedProps"].get("poster")) for e in out] == [("A", "p.jpg"), ("B", None)]
    assert "poster" not in prev["events"][1]["extendedProps"]   # the previous feed isn't changed


def test_every_theater_within_15_miles_is_configured():
    c = fresh_cfg()
    added = {"amc_cherry_creek": "AAADR", "cinemark_belmar": "AARMQ", "regal_river_point": "AAVKZ",
             "cinemark_aurora": "AAJNI", "regal_southglenn": "AAVRY", "regal_colorado_mills": "AAQQK",
             "amc_bowles": "AABAT", "amc_highlands_ranch": "AAECM", "movie_tavern_aurora": "AAUFX",
             "amc_arapahoe": "AAEWN"}
    assert len(c.theaters) == 32                 # + the ten out to 30 mi (test_scrapers)
    for key, tid in added.items():
        t = c.theaters[key]
        assert t.enabled and t.default_on is False and t.scraper == "fandango" and t.location == tid
        assert 39.5 < t.lat < 39.9 and -105.2 < t.lon < -104.7
    assert [k for k, t in c.theaters.items() if t.default_on] == ["sie", "landmark"]


def test_fandango_theaters_link_their_own_site():
    c = fresh_cfg()
    fandango = {k: t for k, t in c.theaters.items() if t.scraper == "fandango"}
    assert fandango and all((t.site or "").startswith("https://") for t in fandango.values())
    assert c.theaters["amc_highlands_ranch"].site.endswith("/amc-highlands-ranch-24")
    feed = _build_feed(c, [st("A", 19, "amc")], DEN)
    by_key = {t["key"]: t for t in feed["theaters"]}
    assert by_key["amc_highlands_ranch"]["site"].startswith("https://www.amctheatres.com/")
    assert "site" not in by_key["sie"]                        # sells its own tickets: nothing to add


def test_build_feed_carries_default_on():
    c = fresh_cfg()
    feed = _build_feed(c, [st("A", 19, "amc")], DEN)
    by_key = {t["key"]: t for t in feed["theaters"]}
    assert by_key["sie"]["default_on"] is True
    assert by_key["amc"]["default_on"] is False
    assert by_key["amc_westminster"]["default_on"] is False
    assert by_key["regal_colorado"]["default_on"] is False  # enabled via Fandango, off by default


def test_title_variants_from_fandango_and_amc():
    t = fresh_cfg().titles
    for raw, want in [
        ("The Nightmare Before Christmas Re-release", "The Nightmare Before Christmas"),
        ("The Nightmare Before Christmas (RE26)", "The Nightmare Before Christmas"),
        ("The Hunger Games: Sunrise on the Reaping - Super Ticket", "The Hunger Games: Sunrise on the Reaping"),
        ("Elevation (Director's Cut) - Anthony Mackie and George Nolfi in person!", "Elevation"),
        ("Breathless - Part of the Albertine Cinémathèque French Film Festival", "Breathless"),
        ("Whiplash - FREE SHOW", "Whiplash"),
        ("Café Flesh - IFS Underground", "Café Flesh"),
        ("Film Screening: Little Amélie or the Character of Rain", "Little Amélie or the Character of Rain"),
        ("Friday Night Weird: These People", "These People"),
        ("Cinema Classics with Jeffrey Kash: Modern Times", "Modern Times"),
        ("The Hunger Games: Sunrise on the Reaping Early Access",
         "The Hunger Games: Sunrise on the Reaping"),
        ("Sinners Early Access Screening", "Sinners"),
        ("The Release", "The Release"),      # a real title ending in "release" is untouched
    ]:
        assert normalize_title(raw, t.strip_prefixes, t.strip_suffixes) == want


# ---- a failing theater keeps its last published showtimes ----------------------------------------

def _event(title, theater, day):
    return {"id": f"{theater}-{title}", "title": title, "start": f"{day.isoformat()}T19:00:00-07:00",
            "allDay": False, "extendedProps": {"theater": theater}}


@pytest.fixture
def flaky_site(tmp_path, monkeypatch):
    """Two theaters with a previous feed on disk; returns (config path, set the flaky fetch)."""
    today = datetime.now(DEN).date()   # Denver's date, as the pipeline uses (the runner is on UTC)
    out = tmp_path / "data.json"
    out.write_text(json.dumps({"events": [
        _event("Old Good Film", "good", today + timedelta(days=30)),
        _event("Long Gone", "flaky", today - timedelta(days=30)),
        _event("Upcoming", "flaky", today + timedelta(days=30)),
    ]}), encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text(f'output = "{out.as_posix()}"\n'
                      '[theaters.good]\nname = "Good"\n'
                      '[theaters.flaky]\nname = "Flaky"\n', encoding="utf-8")
    state = {"fetch": lambda: []}

    class Scraper:
        def __init__(self, cfg, tc, key=None):
            self.key = key

        def fetch(self, start, end):
            return [st("Fresh Film", 19, "good")] if self.key == "good" else state["fetch"]()

    monkeypatch.setattr(pipeline, "SCRAPERS", {"good": Scraper, "flaky": Scraper})
    monkeypatch.chdir(tmp_path)        # diff_new_titles writes known_titles.txt to the cwd
    return config, state


def _raise():
    raise RuntimeError("blocked")


@pytest.mark.parametrize("fetch", [lambda: [], _raise], ids=["no rows", "exception"])
def test_failed_theater_keeps_upcoming_rows(flaky_site, fetch):
    config, state = flaky_site
    state["fetch"] = fetch
    feed = run(str(config))
    titles = {e["title"] for e in feed["events"]}
    assert feed["stale_theaters"] == ["flaky"]
    assert titles == {"Fresh Film", "Upcoming"}   # past rows age out; healthy theater is replaced
    assert feed["films"] == ["Fresh Film", "Upcoming"]


def test_healthy_run_replaces_everything(flaky_site):
    config, state = flaky_site
    state["fetch"] = lambda: [st("New Flaky Film", 20, "flaky")]
    feed = run(str(config))
    assert feed["stale_theaters"] == []
    assert {e["title"] for e in feed["events"]} == {"Fresh Film", "New Flaky Film"}


def test_end_only_from_a_runtime_and_language_from_the_title(flaky_site):
    """No runtime, no end: the page shows only the start rather than a guessed end time."""
    config, state = flaky_site
    timed = st("Timed", 18, "flaky"); timed.runtime_minutes = 95
    state["fetch"] = lambda: [timed, st("Tokyo Godfathers (Subtitled)", 20, "flaky")]
    feed = run(str(config))
    ev = {e["title"]: e for e in feed["events"]}
    assert "end" not in ev["Fresh Film"] and "end" not in ev["Tokyo Godfathers"]
    assert ev["Timed"]["end"].startswith("2026-06-19T19:35")
    assert ev["Tokyo Godfathers"]["extendedProps"]["lang"] == "Subtitled"


def test_cli_publishes_but_exits_nonzero_when_a_theater_fails(flaky_site, tmp_path):
    config, _ = flaky_site
    summary = tmp_path / "summary.md"
    rc = cli.main(["--config", str(config), "--summary", str(summary)])
    assert rc == cli.EXIT_THEATER_FAILED
    written = json.loads((tmp_path / "data.json").read_text(encoding="utf-8"))
    assert "Upcoming" in {e["title"] for e in written["events"]}   # still written, so it deploys
    assert "❌ failed, kept 1 from the last feed" in summary.read_text(encoding="utf-8")


def test_cli_dry_run_reports_failure_without_writing(flaky_site, tmp_path):
    config, _ = flaky_site
    before = (tmp_path / "data.json").read_text(encoding="utf-8")
    assert cli.main(["--config", str(config), "--dry-run"]) == cli.EXIT_THEATER_FAILED
    assert (tmp_path / "data.json").read_text(encoding="utf-8") == before
    assert not (tmp_path / "known_titles.txt").exists()


def test_cli_exits_zero_when_all_theaters_succeed(flaky_site):
    config, state = flaky_site
    state["fetch"] = lambda: [st("New Flaky Film", 20, "flaky")]
    assert cli.main(["--config", str(config), "--dry-run"]) == 0


def test_summary_flags_big_drops_and_lists_new_titles():
    theaters = [{"key": "a", "name": "Theater A"}, {"key": "b", "name": "Theater B"}]
    day = date(2026, 1, 1)
    prev = {"events": [_event(str(i), "a", day) for i in range(10)] + [_event("x", "b", day)]}
    feed = {"theaters": theaters, "stale_theaters": [],
            "events": [_event("1", "a", day), _event("x", "b", day)]}
    out = render_summary(feed, prev, ["Brand New Film"])
    assert "| Theater A | 10 | 1 | ⚠️ dropped by more than half |" in out
    assert "| Theater B | 1 | 1 | ✅ |" in out
    assert "- Brand New Film" in out


# ---- Nov 2026 cleanup rules and the "may need a rule" review ----------------------------------

def test_normalize_title_nov_2026_variants():
    t = fresh_cfg().titles
    for raw, want in [
        ("The Angry Birds Movie: 10th Anniversary (2026)", "The Angry Birds Movie"),
        ("Dune: Part One Reissue", "Dune: Part One"),
        ("Dune: Part Two Reissue (2026)", "Dune: Part Two"),
        ("Crunchyroll Anime Nights: Dive In Wonderland", "Dive In Wonderland"),
        ("Big Dose of Reality Screening: Join the Club", "Join the Club"),
        ("Initial Dose of Reality: Tight & Nerdy", "Tight & Nerdy"),
        ("Sight & Sound Presents: Joshua Live!", "Joshua Live!"),
        ("The Metropolitan Opera: Carmen Encore", "The Metropolitan Opera: Carmen"),
        ("Some Film:", "Some Film"),                       # dangling separator
        ("Heated Rivalry: Episodes 1 & 2", "Heated Rivalry: Episodes 1 & 2"),   # real subtitle
        ("Mission: Impossible", "Mission: Impossible"),
    ]:
        assert normalize_title(raw, t.strip_prefixes, t.strip_suffixes) == want


def test_is_non_film_drops_esports():
    drop = fresh_cfg().titles.drop
    assert is_non_film("League of Legends Worlds 26 - Finals in Theater", drop)
    assert not is_non_film("Rammstein - Live in Mexico City", drop)   # concert films stay


def test_merge_case_variants_uses_most_common_spelling():
    shows = [st("The Only Living Pickpocket in New York"), st("The Only Living Pickpocket in New York"),
             st("The Only Living Pickpocket In New York"), st("Dive In Wonderland"),
             st("Dive in Wonderland")]
    pipeline.merge_case_variants(shows)
    assert {s.film_title for s in shows} == {"The Only Living Pickpocket in New York",
                                             "Dive In Wonderland"}   # tie -> alphabetical first


def test_review_titles_flags_likely_rule_candidates():
    films = ["Dive in Wonderland", "Crunchyroll Anime Nights: Dive In Wonderland",
             "Shorts Package: Mirrors", "Shorts Package: Truth", "Rammstein - Live in Mexico City",
             "Wildwood", "Rocky", "I Play Rocky"]
    new = ["Crunchyroll Anime Nights: Dive In Wonderland", "Shorts Package: Mirrors",
           "Rammstein - Live in Mexico City", "Wildwood", "I Play Rocky"]
    flagged = dict(pipeline.review_titles(new, films))
    assert "variant of “Dive in Wonderland”" in flagged["Crunchyroll Anime Nights: Dive In Wonderland"]
    assert "several titles" in flagged["Shorts Package: Mirrors"]
    assert "Live" in flagged["Rammstein - Live in Mexico City"]
    assert "Wildwood" not in flagged and "I Play Rocky" not in flagged


def test_summary_lists_review_flags():
    feed = {"theaters": [], "stale_theaters": [], "events": []}
    out = render_summary(feed, None, ["X: Y"], [("X: Y", "contains “Live”")])
    assert "| X: Y | contains “Live” |" in out


def test_dry_run_reports_new_titles_without_recording_them(tmp_path):
    known = tmp_path / "known.txt"
    known.write_text("Old\n", encoding="utf-8")
    assert diff_new_titles(["Old", "New"], known, update=False) == ["New"]
    assert known.read_text(encoding="utf-8") == "Old\n"


def test_denver_openings_remember_the_first_showtime_and_forget_old_ones():
    today = date(2026, 11, 6)
    ev = lambda t, day: {"title": t, "start": f"{day}T19:00:00-07:00", "extendedProps": {}}
    previous = {"Wildwood": "2026-10-22", "Long Gone": "2025-06-01", "Recently Gone": "2026-09-01"}
    out = pipeline.denver_openings([ev("Wildwood", "2026-11-06"), ev("Club Kid", "2026-11-19"),
                                    ev("Club Kid", "2026-11-20")], previous, today)
    assert out["Wildwood"] == "2026-10-22"          # opening never moves later
    assert out["Club Kid"] == "2026-11-19"          # upcoming opening: its first scheduled day
    assert out["Recently Gone"] == "2026-09-01"     # not playing, but recent enough to keep
    assert "Long Gone" not in out                   # forgotten after OPENINGS_KEEP_DAYS


def test_trend_blends_tmdb_and_wikipedia_ranks_50_50():
    meta = {
        "A": {"tmdb_id": 1, "popularity": 900, "wiki_views": 10_000},   # tmdb #1, wiki #3 -> 2.0
        "B": {"tmdb_id": 2, "popularity": 500, "wiki_views": 900_000},  # tmdb #2, wiki #1 -> 1.5
        "C": {"tmdb_id": 3, "popularity": 100, "wiki_views": 50_000},   # tmdb #3, wiki #2 -> 2.5
        "D": {"tmdb_id": 4, "popularity": 50},                          # no article: tmdb rank alone
        "Event": {"title": "x"},                                       # no TMDB match: no score
    }
    pipeline.add_trend(meta)
    assert [meta[k]["trend"] for k in "ABCD"] == [2.0, 1.5, 2.5, 4.0]
    assert "trend" not in meta["Event"]


def test_wiki_views_fall_back_to_last_run(monkeypatch):
    monkeypatch.setattr(pipeline, "weekly_views", lambda ids, today: {1: 500})
    meta = {"A": {"tmdb_id": 1}, "B": {"tmdb_id": 2}, "C": {"tmdb_id": 3}}
    previous = {"Old name": {"tmdb_id": 2, "wiki_views": 77}}
    pipeline.add_wiki_views(meta, previous, date(2026, 11, 6))
    assert meta["A"]["wiki_views"] == 500 and meta["B"]["wiki_views"] == 77 and "wiki_views" not in meta["C"]


def test_look_ahead_adds_far_showings(tmp_path, monkeypatch):
    """Sources that can look months ahead (the Sie lists 35mm runs early) add those showings."""
    today = datetime.now(DEN).date()   # Denver's date, as the pipeline uses (the runner is on UTC)
    far = datetime.combine(today + timedelta(days=40), datetime.min.time()).replace(hour=19, tzinfo=DEN)
    config = tmp_path / "config.toml"
    config.write_text(f'output = "{(tmp_path / "data.json").as_posix()}"\n[theaters.sie]\nname = "Sie"\n',
                      encoding="utf-8")

    class Scraper:
        def __init__(self, cfg, tc, key=None):
            self.key = key

        def fetch(self, start, end):
            return [st("Fresh Film", 19, "sie")]

        def fetch_ahead(self, start, end):
            assert start > today + timedelta(days=14)
            return [Showtime(theater="sie", theater_name="Sie", film_title="Cameron Winter at Carnegie Hall on 35mm", start=far),
                    Showtime(theater="sie", theater_name="Sie", film_title="Some Digital Film", start=far)]

    monkeypatch.setattr(pipeline, "SCRAPERS", {"sie": Scraper})
    monkeypatch.chdir(tmp_path)
    feed = run(str(config))
    by_title = {e["title"]: e for e in feed["events"]}
    assert "Some Digital Film" in by_title
    winter = by_title["Cameron Winter at Carnegie Hall"]
    assert winter["extendedProps"]["fmt"] == "35mm"            # moved off the title
