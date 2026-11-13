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
    status_code, headers = 200, {}
    def __init__(self, data): self.data = data
    def raise_for_status(self): pass
    def json(self): return self.data


def test_weekly_views_sums_the_last_seven_full_days(monkeypatch):
    monkeypatch.setattr(wikipedia.httpx, "Client", FakeClient)
    out = wikipedia.weekly_views([10, 11, 12], date(2026, 11, 6), pause=0)
    assert out == {10: 350}                                   # failed and missing articles are left out


# ---- Metacritic from article text ----

def test_metacritic_in_reads_the_template_and_the_usual_sentences():
    m = wikipedia.metacritic_in
    assert m("==Critical response==\n{{Metacritic film prose|77|45|universal acclaim}}") == 77
    assert m("Metacritic, which uses a weighted average, assigned the film a score of 79 out of 100, based on 51 critics") == 79
    assert m("On Metacritic, the film has an 81 out of 100 rating, based on 34 critics") == 81
    assert m("Metacritic assigned the film a rating of 49 out of 100 based on 18 reviews") == 49
    assert m("Rotten Tomatoes gives it 92% and an average rating of 7.5/10.") is None
    assert m("") is None and m(None) is None


def test_metacritic_in_prefers_the_reception_section():
    """A video game's score earlier in the article isn't the film's."""
    text = ("The 2017 game holds a Metacritic score of 85/100.\n\n== Reception ==\n"
            "On Metacritic, the film has a weighted average score of 46 out of 100.")
    assert wikipedia.metacritic_in(text) == 46


class ArticleClient(FakeClient):
    """Wikidata finds three articles (one non-ASCII); the article API serves two of them."""
    def post(self, url, data):
        return Resp({"results": {"bindings": [
            {"tmdb": {"value": "10"}, "article": {"value": "https://en.wikipedia.org/wiki/Wild_Horse_Nine"}},
            {"tmdb": {"value": "11"}, "article": {"value": "https://en.wikipedia.org/wiki/Am%C3%A9lie"}},
            {"tmdb": {"value": "12"}, "article": {"value": "https://en.wikipedia.org/wiki/Gone_Page"}}]}})

    def get(self, url, params=None):
        assert "Amélie" in params["titles"]   # decoded once, not sent as %C3%A9
        return Resp({"query": {"pages": [
            {"title": "Wild Horse Nine", "revisions": [{"slots": {"main": {"content":
                "==Reception==\nMetacritic, which uses a weighted average, assigned the film a score of 77 out of 100"}}}]},
            {"title": "Amélie", "revisions": [{"slots": {"main": {"content": "No scores here."}}}]},
            {"title": "Gone Page", "missing": True}]}})


def test_metascores_reads_articles_and_leaves_out_unread_ones(monkeypatch):
    monkeypatch.setattr(wikipedia.httpx, "Client", ArticleClient)
    assert wikipedia.metascores([10, 11, 12], pause=0) == {10: 77, 11: None}


def test_add_metacritic_keeps_last_runs_score_only_when_the_article_was_not_read(monkeypatch):
    from movie_scraper import pipeline
    monkeypatch.setattr(pipeline, "metascores", lambda ids: {1: 81, 2: None})
    meta = {"Read": {"tmdb_id": 1}, "No score now": {"tmdb_id": 2}, "Unread": {"tmdb_id": 3}}
    previous = {"Read": {"tmdb_id": 1, "metacritic": 70}, "No score now": {"tmdb_id": 2, "metacritic": 55},
                "Unread": {"tmdb_id": 3, "metacritic": 64}}
    pipeline.add_metacritic(meta, previous)
    assert meta["Read"]["metacritic"] == 81              # this run's reading wins
    assert "metacritic" not in meta["No score now"]      # the article no longer gives one
    assert meta["Unread"]["metacritic"] == 64            # couldn't read it: keep last run's


def test_a_429_waits_as_asked_then_reads(monkeypatch):
    waits = []
    monkeypatch.setattr(wikipedia.time, "sleep", waits.append)

    class Busy:
        def __init__(self): self.n = 0
        def get(self, url, params=None):
            self.n += 1
            if self.n == 1:
                r = Resp({}); r.status_code, r.headers = 429, {"Retry-After": "7"}
                return r
            return Resp({"query": {}})

    assert wikipedia._get(Busy(), wikipedia.API, {"a": 1}) == {"query": {}} and waits == [7]


# ---- The language a film was made in, from Wikidata ----

class LangClient(FakeClient):
    def post(self, url, data):
        assert "P364" in data["query"]
        return Resp({"results": {"bindings": [
            {"tmdb": {"value": "1"}, "n": {"value": "1"}, "lang": {"value": "de"}},   # one language
            {"tmdb": {"value": "2"}, "n": {"value": "3"}, "lang": {"value": "ca"}},   # several: unordered
            {"tmdb": {"value": "3"}, "n": {"value": "1"}}]}})                       # no two-letter code


def test_original_languages_keeps_films_with_one_coded_language(monkeypatch):
    monkeypatch.setattr(wikipedia.httpx, "Client", LangClient)
    assert wikipedia.original_languages([1, 2, 3]) == {1: "de"}


def test_original_languages_is_none_when_wikidata_fails(monkeypatch):
    class Down(FakeClient):
        def post(self, url, data): raise RuntimeError("503")
    monkeypatch.setattr(wikipedia.httpx, "Client", Down)
    assert wikipedia.original_languages([1]) is None


def test_add_languages_prefers_wikidata_and_keeps_last_run_when_unreachable(monkeypatch):
    from movie_scraper import pipeline
    meta = lambda: {"Fatherland": {"tmdb_id": 1, "lang": "pl", "intl": True},
                    "The Fifth Element": {"tmdb_id": 18, "lang": "fr", "intl": True},
                    "Fjord": {"tmdb_id": 4, "lang": "ro", "intl": True}}
    monkeypatch.setattr(pipeline, "original_languages", lambda ids: {1: "de", 18: "en"})
    m = meta()
    pipeline.add_languages(m, None)
    assert m["Fatherland"]["lang"] == "de"                                       # TMDB's is the title's
    assert m["The Fifth Element"]["lang"] == "en" and not m["The Fifth Element"]["intl"]
    assert m["Fjord"]["lang"] == "ro"                                            # nothing from Wikidata: TMDB's

    monkeypatch.setattr(pipeline, "original_languages", lambda ids: None)        # Wikidata down this run
    again = meta()
    pipeline.add_languages(again, m)
    assert again["Fatherland"]["lang"] == "de" and again["The Fifth Element"]["lang"] == "en"
