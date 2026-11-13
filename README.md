# Denver Movie Showtimes

What's playing in Denver, one day at a time: every film at the theaters you pick, with posters,
times, tickets and add-to-calendar. A companion to Corey McGinnis's newsletter
[The Movie Newsletter](https://coreymcginnis.substack.com/).

**Live:** https://coreymcginnis1.github.io/denver-showtimes/

- **32 theaters**, from the Sie and the Mayan to the Alamos, AMC, Regal, Harkins, Cinemark and
  Boulder's Dairy Arts Center and CU film series. Readers pick theaters by name or by distance from
  their zip; the Sie and the Mayan start checked.
- **Show** all films, new releases, repertory, or only those **on film** (35mm, 70mm and other
  prints). **Sort** by newest, trending, Metacritic score or A–Z. **All dates** looks up to 90 days ahead where the
  theater publishes that far.
- **Find a film** by title, director, actor or genre.
- Tap a film (title or poster) for its own page: the director, Metacritic score, synopsis and a
  Letterboxd link, then every date it plays and every theater showing it, nearest first (linkable:
  `#film/wild-horse-nine`). Tap a time for tickets and
  add-to-calendar (Google, Outlook, Apple).

[CLAUDE.md](CLAUDE.md) is the detailed guide: every design decision, data rule and what's on hold.

## How it works

```
scrapers → title cleanup → TMDB match → trending, openings → public/data.json → static site → GitHub Pages
```

Everything runs in GitHub Actions ([`.github/workflows/update.yml`](.github/workflows/update.yml));
nothing runs on anyone's computer.

| When | What happens |
|---|---|
| Daily from 3:07 am Denver time, or **Run workflow** | Scrape every theater → commit `public/data.json` and `known_titles.txt` → publish. GitHub starts scheduled runs late or skips them, so there's an attempt every hour until one gets through. |
| Push to `main` | Publish the site without scraping |
| Pull request | Tests, plus a scrape from GitHub's network that writes nothing |

The site in `public/` is plain HTML, CSS and JavaScript with no build step and no libraries. It
loads `data.json` and does everything else in the browser.

## Theaters and sources

| Theaters | Source |
|---|---|
| Sie FilmCenter | Eventive's public API |
| Landmark Mayan, Landmark Greenwood Village | Landmark's showtime API |
| Alamo Drafthouse Sloans Lake, Westminster, Littleton | Alamo's schedule API |
| Dairy Arts Center, Boulder | The Dairy's public events API (WordPress / The Events Calendar) |
| International Film Series, CU Boulder | CU's public campus calendar (Localist API) |
| 24 chain theaters: AMC, Regal, Harkins, Cinemark, Emagine, Movie Tavern | Fandango's showtime JSON (the chains' own sites block scrapers). Tickets link to Fandango, with a link to the theater's own site beside it. |

The list covers every year-round theater within 30 miles of zip 80218. Theaters, their
coordinates and sources live in [`config.toml`](config.toml).

Each film is matched to [TMDB](https://www.themoviedb.org/) for its poster, director, cast,
genres and synopsis, and renamed to TMDB's title so every theater's version of it merges into one
listing. "Trending" blends TMDB popularity with a week of English Wikipedia page views; the Metacritic
score on a film's page is the one its Wikipedia article reports (Metacritic has no free API).

## Running and troubleshooting

No local setup is needed:

- **Refresh now:** on GitHub, **Actions → Update showtimes → Run workflow**.
- **See what happened:** open the run. Its summary has showtimes per theater compared with the last
  feed, TMDB coverage, and new titles worth checking for a cleanup rule.
- **When a theater fails:** it keeps its upcoming showtimes from the last feed, the site still
  publishes with a note for readers, and the run is marked failed so GitHub emails you. Check that
  failed-workflow emails are on under GitHub **Settings → Notifications → Actions**.
- **A wrong or missing film match:** add the film's TMDB id under `[tmdb.overrides]` in
  `config.toml` (see the comments there).
- **Change something:** use a Claude Code session at [claude.ai/code](https://claude.ai/code) or
  GitHub's web editor, and open a pull request.

## Running it on a computer (optional)

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

export TMDB_TOKEN=...                  # TMDB "API Read Access Token"; without it, last run's film data is kept
python -m movie_scraper --dry-run      # scrape and print a summary, write nothing
python -m movie_scraper                # write public/data.json

python -m http.server 8765 --directory public   # then open http://localhost:8765/
pytest                                          # offline tests against saved responses
```

Flags: `--theater KEY` (repeatable), `--dry-run`, `--output PATH`, `--summary PATH`,
`--compare-trending`, `-v`. The command exits with code 3 if any theater failed.

## Configuration: `config.toml`

- `timezone`; `days_ahead` (the two-week window); `ahead_days` (how far theaters that publish
  months ahead are read).
- `[theaters.*]`: `name`, `default_on`, `lat` / `lon` for the distance filter, and the source:
  `scraper` plus `location` (that source's theater id). Fandango theaters also have `site`, their
  own page.
- `[titles]`: cleanup rules for theater titles (series labels, anniversary and event tags, and
  non-film listings to drop). Mirrored in `src/movie_scraper/config.py`; keep the two in sync.
- `[tmdb.overrides]`: fix a match by title. `0` means "not on TMDB"; `"Title @theater"` fixes it
  at one theater only.
- `[filters]` (optional title, weekday and time filters) and `[omdb]` (ratings, switched off).

## Setup

1. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
2. **Settings → Secrets and variables → Actions:** add `TMDB_TOKEN`.
3. Paste the site's address into a Substack post on its own line; Substack shows a preview card
   (`public/preview.png`) that readers click through.

## Project layout

```
src/movie_scraper/    the scraper: cli, pipeline, config, models, tmdb, wikipedia, formats
  scrapers/           one per source: sie_eventive, landmark, alamo, fandango, dairy, cu_ifs
public/               the site: index.html, app.js, styles.css, fonts/, zips.json, data.json
tests/                offline tests and saved responses (tests/fixtures/)
config.toml           theaters, title rules, TMDB overrides
CLAUDE.md             the detailed project guide
```

## Credits, privacy and limits

- Film data and posters from [TMDB](https://www.themoviedb.org/). This product uses the TMDB API
  but is not endorsed or certified by TMDB. Trending and the Metacritic scores come from Wikipedia (page views, and each film's article). The typeface is
  [Archivo](https://fonts.google.com/specimen/Archivo) (SIL Open Font License), served from the site.
- No cookies and no analytics. The only thing a browser stores is the reader's theater picks; the
  zip is never saved. The only outside requests are poster images.
- 24 theaters depend on Fandango's undocumented JSON, so a change there affects all of them at
  once. They'd keep their last showtimes and the run would fail loudly.
- The Sie request uses the public key embedded in Eventive's own site; if it rotates, re-extract
  it (see `scrapers/sie_eventive.py`).
- Times can change. Every showing links to the theater or its ticket seller; confirm there.
