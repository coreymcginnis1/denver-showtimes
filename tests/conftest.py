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
def amc_html():
    return (FIX / "amc_showtimes.html").read_text(encoding="utf-8")


@pytest.fixture
def alamo_schedule():
    return _load("alamo_schedule.json")
