# Denver Movie Showtimes — project guide

A web page of Denver movie showtimes, built as a companion to Corey McGinnis's Substack **The
Movie Newsletter** (https://coreymcginnis.substack.com/). One day at a time: poster cards for
every film playing, that day's schedule, tickets and add-to-calendar. Live at
**https://coreymcginnis1.github.io/denver-showtimes/**, linked from the newsletter.

## Deploy & account rules — IMPORTANT

- This is a **personal** project. Use ONLY the personal GitHub account **`coreymcginnis1`**
  (repo `coreymcginnis1/denver-showtimes`). **Never** push to or use the DRCOG/work account
  **`cmcginnisdrcog`** for this project.
- **The project lives only on GitHub** (no local copy since Nov 2026). Changes are made from
  **Claude Code cloud sessions**: work on a branch, push, open a **PR**, and Corey merges it (or
  asks Claude to). The Claude GitHub App needs write access to this repo; a 403 "Resource not
  accessible by integration" means that lapsed (fix: github.com/apps/claude → configure for
  `coreymcginnis1` → include this repo).
- Corey reviews changes in a **preview** before merging: a private claude.ai page running the PR's
  real `public/` code with that week's data and bundled posters (the page can't load images from
  other sites). Build it from a scratch scrape; don't commit preview files.
- If Corey ever works from his desktop again: both accounts are logged into `gh` there and
  `git push` uses the active one, so `gh auth switch --user coreymcginnis1` before pushing and
  `gh auth switch --user cmcginnisdrcog` after.

## How it runs

```
scrapers → cleanup rules → TMDB match → trending, openings → public/data.json → static site → GitHub Pages
```

`.github/workflows/update.yml` does everything; nothing runs on anyone's computer.

- **Daily at 5:20 am Denver time** (and "Run workflow"): scrape → commit `public/data.json` +
  `known_titles.txt` → publish. Cron is UTC, so it's scheduled at 11:20 and 12:20 UTC and the `gate`
  job lets through only the one that is 5:20 am locally (checks Denver's current UTC offset).
- **Pushes to `main`** publish the site without scraping (frontend changes go live at once).
- **Pull requests** run `pytest` and a `--dry-run` scrape from GitHub's network with the real
  secrets. The dry run prints a `MATCH |` line per film (TMDB id, release, IMDb id) for reviewing
  matches, plus new titles and cleanup-rule suggestions.
- **A theater that fails** (exception or zero rows) keeps its upcoming rows from the last feed and is
  listed in `stale_theaters`; the site still publishes, then the run is marked failed so GitHub
  emails Corey. Each run's summary has a per-theater table (flags drops over half), TMDB coverage
  and the new titles.
- **Nothing piles up:** each run rebuilds `data.json` for today … +14 days; `openings` forget films
  400 days after they last opened; `film_meta`/`tmdb_ids` hold only current films. Events carry only
  the fields the site reads (no nulls), so a daily data commit is ~2.5 MB raw. Git history grows
  ~30–120 MB/year; don't rewrite history to trim it.

### Secrets (repository → Settings → Secrets and variables → Actions)

| Secret | Used for | Notes |
|---|---|---|
| `TMDB_TOKEN` | TMDB "API Read Access Token" | In cloud sessions it's a network secret the proxy injects: run with `TMDB_TOKEN=proxy-injected`. |
| `OMDB_API_KEY` | OMDb (ratings) — currently off | URL-parameter key, so the session proxy can't inject it; test via the PR check. |

Without a token, or when TMDB/Wikipedia error, a run keeps last run's metadata and never fails.
Tests never touch the network (`tests/conftest.py` unsets tokens and stubs Wikipedia).

### Code map

- `src/movie_scraper/` — `python -m movie_scraper` (`--theater KEY`, `--dry-run`, `--output`,
  `--summary`, `--compare-trending`, `-v`). Python 3.11+; httpx, pydantic.
  - `scrapers/` — `sie_eventive.py`, `landmark.py`, `alamo.py`, `fandango.py` (AMC/Regal/Harkins).
  - `pipeline.py` — cleanup, TMDB standardization, openings, trending, feed, run summary.
  - `tmdb.py` · `wikipedia.py` · `omdb.py` (off) · `config.py` · `cli.py` · `models.py`.
- `public/` — `index.html`, `styles.css`, `app.js` (vanilla, no build), `zips.json`,
  `tmdb-logo.svg`, `preview.png`, `data.json` (written by the workflow).
- `config.toml` — theaters, cleanup rules, TMDB overrides, feature switches.
- `tests/` — offline, against saved fixtures in `tests/fixtures/`.

### `data.json`

`theaters` (key, name, color, default_on, lat, lon) · `films` · `events` (`id`, `title`, `start`,
optional `end`/`allDay`, `extendedProps`: `theater`, `screen`, `fmt`, `ticketUrl`, `poster`,
`rating`, `runtime`, `year`, `release`) · `film_meta` (displayed title → TMDB data, `trend`,
`wiki_views`, …) · `tmdb_ids` (local title → TMDB id) · `openings` (title → Denver opening date) ·
`stale_theaters` · `generated_at` · `timezone`.

## Theaters (`config.toml` `[theaters.*]`)

Ten theaters. Sie and Landmark Mayan start on; the rest have `default_on = false`.
One scraper can back several theaters via `scraper` + `location`. `lat`/`lon` drive the distance
filter.

| Theater | Source |
|---|---|
| Sie FilmCenter | Eventive public API (`api.eventive.org`, embedded publishable key) |
| Landmark Mayan / Greenwood Village | landmarktheatres.com boxofficeapi `schedule` endpoint; `location` X02AK / X0873 |
| AMC 9+CO 10 / Westminster Promenade 24 | **Fandango** `napi/theaterMovieShowtimes/<id>`; AAYUA / AAECN |
| Regal UA Denver Pavilions / Colorado Center | **Fandango**; AAJJG / AAFXW |
| Harkins Arvada 14 / Northfield 18 | **Fandango**; AAYFG / AATYG |
| Alamo Drafthouse Sloans Lake | `drafthouse.com/s/mother/v2/schedule/venue/sloans-lake` (JSON) |

- **AMC, Regal and Harkins come from Fandango:** amctheatres.com and regmovies.com block scrapers
  (Cloudflare / bot challenges); Fandango's `napi` JSON is open over plain httpx, and its ticket
  links work. Fandango silently serves a grey "F" placeholder image when it lacks a poster.
- **Coverage checked Nov 2026** (within 10 mi of 80206): also on Fandango but not added — AMC Dine-In
  Cherry Creek 8 (AAADR; 12 of 13 films duplicated elsewhere), Regal River Point, Cinemark Bel Mar
  16, Cinemark Century Aurora, Regal SouthGlenn. The Esquire closed July 2024. Alamo Westminster and
  Littleton are beyond 10 mi.
- **Regal Colorado Center** shrank from ~20 films / ~430 showtimes (July) to ~5–6 / ~115 (Nov 2026)
  while the feed stayed healthy, so the theater itself is running fewer screens. If it drops to
  zero, check regmovies.com in a browser before treating it as a scraper failure.

## Titles

### Cleanup rules (`config.toml` `[titles]`, mirrored in `config.py` `DEFAULT_*` — keep in sync)

Prefer **general** patterns over one-offs.

- `strip_prefixes` — series/presenter labels: Bleak Week, Scream Screen, The Popcorn List, Sci-Fi
  Film Series, Fan Faves, Staff Pick, Crunchyroll Anime Nights, Sie's "… Dose of Reality
  [Screening]", any "<Presenter> Presents:".
- `strip_suffixes` — release year `(2026)`, `Nth Anniversary` (paren/colon forms), `… Cut`,
  `… Edition`, `Re-release`/`Reissue`/`(RE26)`, `Encore`/`(2026 Encore)`, language versions
  (`(English 2026)`, `(Hindi Dubbed)`), `on 35mm` (gauge kept as the format), `(dir. X)`, Sensory
  Friendly, sponsor tags, Fan Event / Early Access / Promo / Preview screenings, `w/ …`.
- `drop` — not films: mystery screenings (Screen Unseen, Mystery Movie, Harkins Secret Cinema),
  private rentals, members-only, memorials, watch parties, live sports and esports. Concerts, opera,
  NT Live and TV-episode screenings are **kept**.
- `normalize_title()` also fixes ALL-CAPS/lowercase titles and dangling `:`/`-`;
  `merge_case_variants()` merges titles differing only in case.
- **TOML gotcha:** single-quoted TOML strings can't contain an apostrophe — use `\W?` or double quotes.

### TMDB is the standard name (`tmdb.py`, `pipeline.standardize_titles()`, `[tmdb]`)

After cleanup every film is matched to TMDB and **renamed to TMDB's title** (casing cleaned by
`recase()`), so each theater's variant of a film merges. Two films with the same TMDB title get the
year appended.

- **Strict matching** (a wrong match renames the film on the site): exact title or TMDB title +
  ": subtitle", possessive credits dropped, and a year hint — the year Sie/Landmark state beats
  Fandango's `releaseDate` (a revival's may be the re-release). No fuzzy guessing.
- Wrong or missing match → `[tmdb.overrides]` (local title → id from themoviedb.org/movie/<id>).
  Matches are remembered in `tmdb_ids`.
- **Special events = no TMDB movie match:** TV episodes (Heated Rivalry), double features, shorts
  programs, one-night events. The site sorts them last, leaves them out of New releases /
  Repertory, and gives them no "new" tag. A real film missing from TMDB lands here too — fix with
  an override.

### New-titles digest

Each run lists titles new since the last (tracked in `known_titles.txt`; dry runs don't record), and
`review_titles()` flags likely rule candidates (labels wrapped around a known title, a shared
"Label:", event/edition words, stray punctuation). It only flags; rules stay manual.

## Sorting data

- **Denver opening** (`openings`, `pipeline.denver_openings()`): the first day a film had a showtime
  at any theater we track; only moves earlier. Used instead of TMDB's date (often a festival or
  foreign release: Fatherland Jun 19 vs Denver Nov 6) or Fandango's (national / NY-LA limited).
  Backfilled from `data.json` history from June 2026.
- **Repertory** = first released more than **two years** before its Denver opening (`REPERTORY_DAYS`
  in `app.js`). Two, not one: indie films often reach Denver a year+ after a festival premiere.
- **Trending** (`film_meta.trend`, `pipeline.add_trend()`, `[trending]`): the average of a film's
  rank by TMDB popularity and by English Wikipedia page views over the last 7 days (TMDB rank alone
  without an article). Views: Wikidata finds the article by TMDB id (P4947), the Wikimedia pageviews
  API gives daily counts; free, needs only a descriptive User-Agent. **Why 50/50 (Nov 2026):**
  against Letterboxd's popular-this-week list (10 overlapping films) rank correlation was TMDB
  0.59, Wikipedia 0.77, blend 0.90 (40–60% all ~0.88). TMDB alone is worldwide and counts streaming
  (The Mongoose #3); Wikipedia alone over-weights big international releases (Ramayana #1). There
  is no free city/state-level source (Wikimedia publishes none; Google Trends has no API). Wikimedia
  blocks the cloud-session proxy, so check it through the PR check (`--compare-trending` prints a
  side-by-side table).

## Decisions and what's on hold (don't redo without new information)

- **No ratings.** TMDB ratings come from a few hundred voters; IMDb's data is personal-use only;
  Metacritic / Rotten Tomatoes have no API and forbid scraping; OMDb leaves most current releases
  unscored for weeks (Wild Horse Nine blank while Metacritic showed 78) and lags on IMDb ratings
  (You Can See Everything 7.9 from 165 votes vs 9.1 from 27K). `omdb.py` is kept with
  `[omdb] enabled = false`; turning it back on also needs the site display rebuilt.
- **Letterboxd:** its terms forbid robots/scrapers (RSS feeds included — not explicitly
  authorized) and its API is by application (api@letterboxd.com); Corey chose not to apply for
  now. The site only **links** to `letterboxd.com/tmdb/<id>/`. A member's own data export (CSV) is
  the one legitimate source if a "Corey's ratings" feature is ever wanted.
- **Tags on hold:** "Indie" and "International" are computed (`tmdb.classify()`, `film_meta.indie` /
  `.intl`) but **not shown**. Indie mislabeled classics (TMDB lists producers, not distributors);
  Corey wants both or neither.
- **Other trending sources checked:** TMDB weekly trending list (58% coverage), Trakt (streaming),
  IMDb popularity / box office / Google Trends (no license or API).
- **Removed:** "Corey's picks" pre-selection (went stale) and "My list" (little use, no sync).
- **Hosting:** GitHub Pages (~100 GB/month soft limit ≈ 300K visits). A nicer address: a free
  `denvershowtimes` GitHub organization (denvershowtimes.github.io) or a ~$12/yr domain pointed at
  Pages, with a redirect from the old link. Not done yet.

## Frontend (`public/`)

Redesigned Nov 2026, Letterboxd-inspired but its own look. Dark warm palette (`--bg #15110e`,
cream `--paper`, newsletter brick `--brick-fill #C0432B`); Newsreader (titles) + Schibsted Grotesk
(UI), **self-hosted** in `public/fonts/` (latin + latin-ext woff2, OFL licenses alongside) so no visit
reports to Google. Title "Denver Movie Showtimes", upright (no italic). Theater colors appear only as dots. Corners: 3px posters (`--r-xs`), 6px buttons/inputs, pills only for filters and toggles.

- **Controls:** day strip ("Next 2 weeks", Today … +14 days; selected day is a plain brick fill) ·
  **Near [zip] 1 / 3 / 5 mi / All** (default **80218** — Sie and the Mayan come first and it holds the
  metro's population-weighted center; **never saved**, so readers aren't tracked; straight-line
  distance from Census zip centroids in `zips.json`, no travel times) · theater chips sorted by
  distance with miles and that day's count (choices saved in `localStorage` with the default set they were made against; changing `default_on` resets everyone to the new defaults) · search.
- **Show:** All · New releases · Repertory. **Sort:** Newest · Trending · A–Z. Films without the
  data sort last.
  - **Newest:** new releases by Denver **release week** (Friday–Thursday; Wed/Thu previews count
    toward the Friday they lead into, `releaseWeek()`), latest and upcoming first, **Trending within
    a week**; then repertory by original release; special events last.
- **Cards:** poster, TMDB title, year · rating · runtime · format tags · "Opening week" (first
  7 days in Denver) / "Opens Nov 19", times grouped by theater, "View on Letterboxd". **Posters:** TMDB `w500`
  first, other theaters' art next, Fandango (600 px renderer) last, then a typeset placeholder; the
  scraper drops Fandango URLs that are the placeholder itself. Long lists clamp behind "Show all N
  theaters" (`clampVenues()`).
- **Schedule:** the day in time order (Morning/Afternoon/Evening/Late; earlier-today rows behind a
  button). Desktop: sticky right column; phone: Films / Schedule toggle.
- **Next 2 weeks:** **Now playing** (a showing today at the selected theaters, or a new release already open in Denver whose next showing is within `RUN_GAP_DAYS` = 3 days; repertory and events need today; by the chosen sort) then **Coming soon** (everything else, repertory included, by its next showing); each
  theater gets one line ("Nov 6–12 · 14 showings") and a "Next …" button. No schedule column.
- **Search** also shows matches beyond the selected theaters/day under "Also playing elsewhere"
  (e.g. Fjord, only at AMC Westminster).
- **Tap a time** → sheet with Get tickets, Google, Outlook, Apple/.ics (ICS uses TZID America/Denver).
- **Times read "3:00 pm"** (lowercase, no periods; `hm12()`); digits tabular, "am/pm" in `.ap`.
- "Floating time": the ISO offset is ignored, so every viewer sees Denver wall-clock times; "now"
  (for dimming past showtimes) is computed in America/Denver.
- **Privacy:** no cookies, no analytics. The only browser storage is the theater pick
  (`dst-theaters` in `localStorage`, never sent anywhere); the zip is never saved. Third-party
  requests are poster images only (TMDB, Fandango, theaters). Keep it that way.
- **Footer** credits TMDB (logo + required notice) and Wikipedia, and links each theater's site.
- **Cache-busting:** `index.html` loads `styles.css`/`app.js` with `?v=__ASSET_VERSION__`, replaced
  with the commit SHA on deploy; `data.json` is fetched `no-store`. OG tags use `__SITE_URL__`.

## Substack

Substack can't embed interactive widgets, so the site stands alone; the newsletter pastes the URL
for a preview card (OG title/description + `public/preview.png`).
