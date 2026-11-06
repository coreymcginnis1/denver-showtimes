"""Wikipedia views, offline: the network calls are replaced."""
from datetime import date

from movie_scraper import wikipedia


class FakeClient:
    def __init__(self, *a, **k): self.urls = []
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def post(self, url, data):
        return Resp({"results": {"bindings": [
            {"tmdb": {"value": "10"}, "article": {"value": "https://en.wikipedia.org/wiki/Wild_Horse_Nine"}},
            {"tmdb": {"value": "11"}, "article": {"value": "https://en.wikipedia.org/wiki/Broken_Page"}}]}})
    def get(self, url):
        self.urls.append(url)
        if "Broken_Page" in url:
            raise RuntimeError("429")
        return Resp({"items": [{"views": 100}, {"views": 250}]})


class Resp:
    def __init__(self, data): self.data = data
    def raise_for_status(self): pass
    def json(self): return self.data


def test_weekly_views_sums_the_last_seven_full_days(monkeypatch):
    monkeypatch.setattr(wikipedia.httpx, "Client", FakeClient)
    out = wikipedia.weekly_views([10, 11, 12], date(2026, 11, 6), workers=1)
    assert out == {10: 350}                                   # failed and missing articles are left out
