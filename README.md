# Denver Indie & Repertory Showtimes

An interactive web calendar of Denver movie showtimes — the three indie/repertory mainstays
**Sie FilmCenter**, **Landmark Mayan**, and **AMC 9+CO 10**, plus opt-in secondary venues
(**AMC Westminster**, **Alamo Drafthouse Sloans Lake**) that occasionally carry indies/70mm/IMAX
— that readers can filter by film and from which they can add any screening to their own
calendar (Google / Outlook / Apple `.ics`). Built to be linked from a Substack post.

## How it works

```
scraper (GitHub Actions)  ──►  public/data.json  ──►  static site (FullCalendar)  ──►  GitHub Pages
   runs every Thursday           the data feed         filter + add-to-calendar        published by the same run
```

- A scheduled **GitHub Action** scrapes each theater, commits `public/data.json`, and publishes
  `public/` to **GitHub Pages**. Nothing runs on a personal computer.
- `public/` is a dependency-free static site (FullCalendar + vanilla JS) that renders the feed.
- You paste the Pages URL into Substack; it renders a preview card that readers click through.
  (Substack can't embed interactive widgets inline — only a fixed allowlist — so the calendar
  lives on its own page and Substack links to it.)

## Data sources

| Theater | Source | Detail |
|---|---|---|
| Sie FilmCenter | Eventive public API (`api.eventive.org`) | Exact showtimes |
| AMC 9+CO 10 | Fandango napi (theater id `AAYUA`) | Exact showtimes + formats, ~2 weeks; tickets link to Fandango |
| Landmark Mayan | `boxofficeapi` `schedule` endpoint | Exact showtimes, screen + format, direct booking links |
| AMC Westminster Promenade 24 | Fandango napi (theater id `AAECN`) | Exact showtimes + formats; tickets link to Fandango; **off by default** |
| Alamo Drafthouse Sloans Lake | "mother" schedule API (`drafthouse.com/s/mother/v2`) | Exact showtimes, screen, special formats (35/70mm); **off by default** |
| Regal Colorado Center / Denver Pavilions | Fandango napi (`fandango.com/napi/theaterMovieShowtimes`) | Exact showtimes + formats (IMAX/RPX), via plain httpx; **off by default** |
| Harkins, Cinemark, Movie Tavern, more AMC and Regal, Alamo Westminster / Littleton, Landmark Greenwood Village | Fandango napi, or the Alamo / Landmark APIs above | Every year-round theater within 15 mi of 80218 (22 in all); **off by default** |

"Off by default" theaters are scraped and available, but their filter chip starts unchecked —
readers click it to add them. **AMC and Regal** read from **Fandango** (one JSON call per date, no
browser) because both chains' own sites block scrapers. Both sell tickets through Fandango, whose
`napi` endpoints are open (see `scrapers/fandango.py`).

## Running and troubleshooting

No local setup is needed for any of this:

- **Refresh now:** on GitHub, **Actions → Update showtimes → Run workflow**.
- **See what happened:** open the run. Its summary has a table of showtimes per theater compared
  with the last feed, plus any new titles to check for a cleanup rule in `config.toml` (`[titles]`).
- **When a theater fails:** it keeps its upcoming showtimes from the last feed instead of vanishing,
  the site still publishes, and the run is marked failed so GitHub emails you. The summary shows
  which theater, and `stale_theaters` in `data.json` lists it too. Check that failed-workflow emails
  are on under GitHub **Settings → Notifications → Actions**.
- **Change something:** use a Claude Code session at [claude.ai/code](https://claude.ai/code), or
  GitHub's web editor, and open a pull request. The PR check runs the tests and a scrape that writes
  nothing, from GitHub's network.

## Running it on a computer (optional)

```bash
python -m venv .venv
.venv\Scripts\activate              # Windows;  source .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"

python -m movie_scraper --dry-run   # preview what would be scraped
python -m movie_scraper             # write public/data.json

python -m http.server 8765 --directory public   # then open http://localhost:8765/
```

Useful flags: `--theater KEY` (repeatable), `--dry-run`, `--output PATH`, `--summary PATH`, `-v`.
The command exits with code 3 if any theater failed.

## Configuration — `config.toml`

- `timezone`, `days_ahead` (rolling window), `default_runtime_minutes`
- `[theaters.*]` — `enabled` (scrape + include), `default_on` (whether its filter chip starts
  ON; set `false` for secondary venues), display `name`, calendar `color`, and optionally
  `scraper` (reuse another theater's scraper class) + `location` (that scraper's theatre id —
  an Alamo venue or a Fandango theater id)
- `[filters]` (optional) — `title_include` / `title_exclude` (regex), `weekdays`,
  `earliest` / `latest` (local `HH:MM`). Empty = include everything.

## Deploy (GitHub Pages + Actions)

1. Push this repo to GitHub.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. The workflow [`.github/workflows/update.yml`](.github/workflows/update.yml) does the rest:

| Trigger | What it does |
|---|---|
| Thursdays at 9am Denver time (8am in winter), or **Run workflow** | Scrape → commit `public/data.json` and `known_titles.txt` → publish |
| Push to `main` | Publish without scraping |
| Pull request touching code or config | Tests, plus a scrape that writes nothing |

Showtimes turn over Wed/Thu, so once a week is plenty. Your calendar will be at
`https://<user>.github.io/<repo>/`.

## Link it from Substack

Paste the Pages URL on its own line in a post and press Enter — Substack renders a preview card
(title, description, and `public/preview.png`). Readers click it to open the live calendar.

## Project layout

```
src/movie_scraper/        scraper package (models, config, pipeline, cli, scrapers/)
public/                   static site (index.html, app.js, styles.css, data.json, preview.png)
tests/                    offline tests + saved fixtures
.github/workflows/        weekly scrape, publish, and PR checks
config.toml               settings
```

## Tests

```bash
pytest                    # runs offline against saved fixtures in tests/fixtures/
```

## Notes & limitations

- All theaters carry exact showtimes. Landmark's come from a live `schedule` endpoint
  the site calls only after a theater is selected (`from`/`to` cinema-day window +
  `theaters={"id":"X02AK",...}`) — see `src/movie_scraper/scrapers/landmark.py`.
- Four of the seven theaters depend on Fandango's undocumented `napi` endpoint, so a change there
  affects all four at once. If that happens they keep their last showtimes and the run fails loudly.
- The Sie/Eventive request uses Eventive's public publishable read key embedded in their site; if
  it ever rotates, re-extract it (see `src/movie_scraper/scrapers/sie_eventive.py`).
- Scraping is for personal/community convenience — times can change; always confirm on the
  theater's site (every entry links out). Be courteous with run frequency.
```
