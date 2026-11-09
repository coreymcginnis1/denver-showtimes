import json
from pathlib import Path

import pytest

from movie_scraper.config import load_config

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def cfg():
    return load_config(ROOT / "config.toml")


@pytest.fixture
def sie_payload():
    return _load("sie_upcoming.json")


@pytest.fixture
def landmark_scheduled():
    return _load("landmark_scheduled.json")


@pytest.fixture
def landmark_schedule():
    return _load("landmark_schedule.json")


@pytest.fixture
def landmark_movies():
    return _load("landmark_movies.json")


@pytest.fixture
def alamo_schedule():
    return _load("alamo_schedule.json")


@pytest.fixture
def fandango_showtimes():
    return _load("fandango_showtimes.json")


@pytest.fixture(autouse=True)
def _no_live_tmdb(monkeypatch):
    """Tests run offline: never let a real TMDB_TOKEN in the environment reach the network."""
    monkeypatch.delenv("TMDB_TOKEN", raising=False)


@pytest.fixture(autouse=True)
def _no_live_omdb(monkeypatch):
    monkeypatch.delenv("OMDB_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_live_wikipedia(monkeypatch):
    """Tests run offline: the pipeline's Wikipedia lookup returns nothing."""
    monkeypatch.setattr("movie_scraper.pipeline.weekly_views", lambda *a, **k: {})


@pytest.fixture
def dairy_events():
    return _load("dairy_events.json")


@pytest.fixture
def cu_ifs_events():
    return _load("cu_ifs_events.json")
