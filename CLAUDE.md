# Denver Movie Showtimes — project guide

An interactive web calendar of Denver movie showtimes, built as a companion to Corey
McGinnis's Substack **The Movie Newsletter** (https://coreymcginnis.substack.com/). Readers
filter by film/theater and add any screening to their own calendar (Google / Outlook / .ics).
Live at **https://coreymcginnis1.github.io/denver-showtimes/**, linked from the newsletter.

## Deploy & account rules — IMPORTANT

- This is a **personal** project. Deploy ONLY to the personal GitHub account
  **`coreymcginnis1`** (repo `coreymcginnis1/denver-showtimes`). **Never** push to or use the
  DRCOG/work account **`cmcginnisdrcog`** for this project.
- **The project lives only on GitHub** (no local copy since Nov 2026). Changes are made from
  **Claude Code cloud sessions** on this repo: work on a branch, push, open a **PR**, and Corey
  merges it (or asks Claude to). The Claude GitHub App needs write access to this repo for
  sessions to push; a 403 "Resource not accessible by integration" means that access lapsed
  (fix: github.com/apps/claude → configure for `coreymcginnis1` → include this repo).
- PR checks run `pytest` plus a `--dry-run` scrape from GitHub's network (only when `src/`,
  `tests/`, `config.toml`, `pyproject.toml` or the workflow change). Merging to `main` publishes
  `public/` to GitHub Pages without scraping; new data comes from the Thursday run or a manual
  **Actions → Update showtimes → Run workflow** (`.github/workflows/update.yml`).
- If Corey ever works from his desktop again: both accounts are logged into `gh` there, and
  `git push` uses the active one, so run `gh auth switch --user coreymcginnis1` before pushing and
  `gh auth switch --user cmcginnisdrcog` after (the work account must stay active for his job).

## How it works

```
scraper (Python, GitHub Actions, weekly)  →  TMDB match  →  public/data.json  →  static site (vanilla JS)  →  GitHub Pages
```

- `src/movie_scraper/` — Python package: per-theater scrapers → normalize/filter/dedupe →
  writes `public/data.json`. Run `python -m movie_scraper` (flags: `--theater KEY` repeatable,
  `--dry-run`, `--output`, `--summary`, `-v`). Python 3.11+; deps: httpx, pydantic.
- `public/` — dependency-free static site (`index.html` + `styles.css` + vanilla `app.js`, Google Fonts only). No build.
- **Scraping runs in GitHub Actions, not on anyone's computer.** `update.yml`: Thursdays 15:00 UTC
  and "Run workflow" scrape → commit `public/data.json` + `known_titles.txt` → publish. Pushes to
  `main` publish without scraping. PRs run `pytest` plus a `--dry-run` scrape from GitHub's network.
- **When a theater fails** (an exception or zero rows) it keeps its upcoming rows from the last feed
  and is listed in `stale_theaters` in `data.json`. The CLI exits 3, the site still publishes, then
  the run is marked failed so GitHub emails Corey. Each run's summary has a per-theater table
  (flags drops of more than half) and the new titles.
- `pytest` runs offline against saved fixtures in `tests/fixtures/`.

## Theaters & data sources (`config.toml` `[theaters.*]`)

Seven theaters. The first three are on by default; the rest have `default_on = false` (their
filter chip starts unchecked — opt-in secondary venues). One scraper class can back several
theaters via `scraper` + `location`.

| Theater | Scraper / source |
|---|---|
| Sie FilmCenter | Eventive public API (`api.eventive.org`, embedded publishable key) |
| Landmark Mayan | `landmarktheatres.com` boxofficeapi `schedule` endpoint (httpx) |
| AMC 9+CO 10 | **Fandango** `napi/theaterMovieShowtimes/<id>` (httpx); `location = AAYUA` |
| AMC Westminster Promenade 24 | same Fandango scraper; `location = AAECN` |
| Alamo Drafthouse Sloans Lake | `drafthouse.com/s/mother/v2/schedule/venue/sloans-lake` (httpx JSON, no browser) |
| Regal UA Colorado Center / Denver Pavilions | **Fandango** `napi/theaterMovieShowtimes/<id>` (httpx) |

- **AMC & Regal quirk (important):** both chains' own sites block scrapers. regmovies.com is
  Cloudflare-gated (it only server-renders the *current day* and 403s httpx), and amctheatres.com
  bot-challenged the old Playwright scraper even from a home IP. Both sell tickets through
  **Fandango**, whose `napi` JSON is open over plain httpx, so both read from there. `location` is
  the Fandango theater id (**AAFXW** = Regal Colorado Center, **AAJJG** = Regal Denver Pavilions,
  **AAYUA** = AMC 9+CO 10, **AAECN** = AMC Westminster). See `scrapers/fandango.py`. Before the
  switch, Fandango matched 115 of 116 AMC showtimes on title and time for one day; the other was
  the same showing under a different title tag. AMC ticket links now go to Fandango.

## Title normalization (`config.toml` `[titles]`)

Scraped titles are messy (special editions, cuts, anniversary/festival tags, series labels,
sponsor tags, member events, live sports). Three **class-based** regex lists keep the film list
clean as new variants appear each week — prefer *general* patterns over one-offs:

- `strip_prefixes` — series/program labels from the front: "Bleak Week: X" → "X"
  (also Scream Screen, The Popcorn List, Sci-Fi Film Series, Fan Faves, Staff Pick, Crunchyroll
  Anime Nights, Sie's "… Dose of Reality [Screening]", and any "<Presenter> Presents:").
- `strip_suffixes` — trailing tags: release year `(2026)`, `Nth Anniversary` (incl. paren and
  colon forms), `Director's/Extended/... Cut`, `... Edition`, `Re-release`/`Reissue`/`(RE26)`,
  `Encore`, `on 35mm[ film]` (the gauge is captured into the format field), `(dir. X)`, Sensory
  Friendly, sponsor tags (Xfinity), Fan Event / Early Access / Promo / Preview screenings, `w/ ...`.
- `drop` — non-films removed entirely: mystery / private-rental / members-only screenings,
  memorial/tribute screenings, watch parties (GOLAZO), live sports and esports (`UFC \d`, Copa
  Mundial, Apple TV Live, League of Legends). Concerts, opera, NT Live and TV-episode screenings
  are deliberately **kept** (they're ticketed screenings people look for).

The `[titles]` lists in `config.toml` mirror the `DEFAULT_*` lists in `config.py`; keep both in sync.

`pipeline.normalize_title()` also title-cases fully UPPER/lowercase titles and down-cases 4+
letter all-caps words (BLEACH→Bleach) so casing variants merge, and drops a dangling `:`/`-` left
by a stripped tag. `pipeline.merge_case_variants()` then gives titles that differ only in case one
spelling (the one most showtimes use), e.g. "Pickpocket in/In New York". `Alien` and `Aliens` are
deliberately kept separate (base titles differ; the picks regex uses a `\b` boundary).

**TOML gotcha:** single-quoted TOML strings **cannot contain an apostrophe** (breaks parsing) —
use `\W?` (e.g. `Director\W?s`, not `Director's`) or double quotes for literals without regex
escapes.

## TMDB: the title standard and the sort data (`src/movie_scraper/tmdb.py`, `config.toml` `[tmdb]`)

After the cleanup rules, every film is matched to TMDB (themoviedb.org) and **renamed to TMDB's
title**, so variants of one film from different theaters merge into one entry without new rules
(`pipeline.standardize_titles()`). TMDB's name gets the same casing cleanup (`recase()`); two
different films sharing a TMDB title get the year appended. Unmatched titles (events, shorts
programs, double features) keep their cleaned-up name. The rules still matter: TMDB only finds
"Bleak Week: Gummo" once the label is stripped, and non-films still need `drop`.

- **Matching is strict on purpose** (a wrong match now renames the film on the site): exact
  title (or TMDB title = ours + ": subtitle"), possessive credit dropped ("Ken Russell's The
  Devils"), and a year hint — the year Sie/Landmark state beats Fandango's `releaseDate`, which
  for a revival can be the re-release date. No fuzzy guessing.
- **Wrong or missing match → `[tmdb.overrides]`** in `config.toml`: normalized local title → TMDB
  id (from the film's themoviedb.org URL). The run summary lists titles TMDB didn't match.
- `data.json` gains `film_meta` (displayed title → `tmdb_id`, `release`, `popularity`,
  `vote_average`, `vote_count`, `tmdb_poster`) and `tmdb_ids` (local title → id, so next week
  reuses matches instead of searching again).
- **Token:** `TMDB_TOKEN` (TMDB "API Read Access Token") — a GitHub Actions repository secret for
  the workflow; in cloud sessions it's a network secret the proxy injects, so run with
  `TMDB_TOKEN=proxy-injected`. Without a token, or if TMDB errors, the run keeps last week's
  metadata and never fails. Tests never call TMDB (`conftest.py` unsets the token).
- **Terms:** TMDB's free API is non-commercial with attribution (footer text + `tmdb-logo.svg`).
  **Letterboxd forbids scraping** (terms of use + robots.txt) and its API is by application only,
  so the site only *links* to Letterboxd (`letterboxd.com/tmdb/<id>/`), never scrapes it. Corey
  chose not to apply for the Letterboxd API for now. Metacritic: no API and no scraping; OMDb
  (free key, non-commercial) carries Metascores if a Metacritic sort is wanted later.

## New-titles digest and cleanup review

Each scrape prints titles that are *new since the last run* (tracked in the committed
`known_titles.txt`), so Corey only eyeballs new/odd titles instead of re-scanning the whole
list. They appear in the Action run's summary. See `pipeline.diff_new_titles()`; the workflow commits
`known_titles.txt`. A `--dry-run` (and so every PR check) reports new titles without recording them.

`pipeline.review_titles()` then flags the new titles most likely to need a rule, with the reason,
in a "may need a cleanup rule" table at the top of the summary: a label wrapped around another
title on the list ("Crunchyroll Anime Nights: X" next to "X"), a "Label:" shared by several titles
(a new series/presenter), or event/edition words and leftover punctuation (`_REVIEW_HINTS`: Live,
Finals, Reissue, Encore, Presents, Screening, trailing `:` …). It only flags; rules stay manual.

## "Corey's picks" (`config.toml` `[defaults].films`) — retired Nov 2026

The list had gone stale, so `films = []`: every film starts selected and the "Corey's picks" button
is hidden (it shows only while `default_films` is non-null). To revive, add case-insensitive regexes
vs the normalized title (e.g. `'Alien\b'`, so "Aliens" doesn't match). If none of the picks plays
today at a theater that starts on, the page pre-selects all films so the calendar never opens empty
(`initialFilms()` in `public/app.js`). **Future idea:** generate the list from Corey's Substack RSS.

## Theater notes

- **Regal UA Colorado Center** shrank steadily from ~20 films / ~430 showtimes per scrape (July)
  to ~5–6 films / ~115 (Nov 2026). The scraper and Fandango feed are healthy (Pavilions, same
  scraper, is normal), so this looks like the theater itself running far fewer screens. Worth
  re-checking on regmovies.com in a browser if it drops to zero (a closure would make it "fail").

## Frontend notes (`public/`)

Redesigned Nov 2026 (Letterboxd-inspired, not a copy): **one day at a time**, no calendar library.

- **Day strip** (today … +14 days; the selected day is a brick "ticket stub"), theater chips
  (default-on theaters from `config.toml`, with that day's counts), search. Sticky on desktop.
- **Poster cards** for every film playing that day at the selected theaters: poster, title (TMDB
  name), year · rating · runtime · ★ TMDB average (only with ≥20 votes) · format tags, then times
  grouped by theater, and a "View on Letterboxd" link. Posters try the theater's image (Fandango's
  first), then TMDB's, then a typeset placeholder.
- **Sorts:** Newest (default; release date, else year) · Popular this week (TMDB popularity) ·
  Top rated (TMDB average shrunk toward 6.5 until ~50 votes) · A–Z. Films with no TMDB data sort last.
- **Schedule** of the day in time order (Morning/Afternoon/Evening/Late; earlier-today rows
  hidden behind a button). Desktop: sticky right column. Phone: Films / Schedule toggle.
- **Tap a time** → sheet with Get tickets, Google, Outlook, Apple/.ics (ICS uses TZID America/Denver).
- **My list** (+ on a poster) and theater choices are saved in `localStorage` (try/catch; optional).
  The schedule can show only My list.
- "Floating time": the ISO offset is ignored; Denver wall-clock shows for every viewer, and
  "now" for dimming past showtimes is computed in America/Denver.
- Dark warm palette (`--bg #15110e`, cream `--paper`, newsletter brick `--brick-fill #C0432B`);
  Newsreader (titles) + Schibsted Grotesk (UI) from Google Fonts. Theater colors are only dots.
- **Cache-busting:** `index.html` references `styles.css`/`app.js` with `?v=__ASSET_VERSION__`;
  the deploy Action replaces `__ASSET_VERSION__` with the commit SHA so frontend changes show
  immediately. `data.json` is fetched with `cache: "no-store"`. OG tags use a `__SITE_URL__`
  placeholder the Action fills in.

## Substack integration

Substack can't embed interactive widgets, so the calendar is its own Pages site; the newsletter
pastes the URL to get a preview card (OG title/description + `public/preview.png`) readers click
through.
