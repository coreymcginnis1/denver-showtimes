# Denver Indie & Repertory Showtimes

An interactive web calendar of Denver movie showtimes — the three indie/repertory mainstays
**Sie FilmCenter**, **Landmark Mayan**, and **AMC 9+CO 10**, plus opt-in secondary venues
(**AMC Westminster**, **Alamo Drafthouse Sloans Lake**) that occasionally carry indies/70mm/IMAX
— that readers can filter by film and from which they can add any screening to their own
calendar (Google / Outlook / Apple `.ics`). Built to be linked from a Substack post.

## How it works

```
scraper (Python, local)  ──►  public/data.json  ──►  static site (FullCalendar)  ──►  GitHub Pages
   you run it weekly             the data feed         filter + add-to-calendar       deploy via Actions
```

- A Python scraper pulls showtimes from each theater and writes `public/data.json`.
- `public/` is a dependency-free static site (FullCalendar + vanilla JS) that renders the feed.
- You run the scraper **on your machine** (weekly — showtimes turn over Wed/Thu) and push
  `data.json`; a **GitHub Action** then publishes `public/` to **GitHub Pages**. Scraping is local
  because AMC blocks cloud datacenter IPs (your home IP works).
- You paste the Pages URL into Substack; it renders a preview card that readers click through.
  (Substack can't embed interactive widgets inline — only a fixed allowlist — so the calendar
  lives on its own page and Substack links to it.)

## Data sources

| Theater | Source | Detail |
|---|---|---|
| Sie FilmCenter | Eventive public API (`api.eventive.org`) | Exact showtimes |
| AMC 9+CO 10 | Rendered showtimes page (Playwright) | Exact showtimes, ~2 weeks |
| Landmark Mayan | `boxofficeapi` `schedule` endpoint | Exact showtimes, screen + format, direct booking links |
| AMC Westminster Promenade 24 | Same AMC scraper, different `location` slug | Exact showtimes; **off by default** |
| Alamo Drafthouse Sloans Lake | "mother" schedule API (`drafthouse.com/s/mother/v2`) | Exact showtimes, screen, special formats (35/70mm); **off by default** |
| Regal Colorado Center / Denver Pavilions | Fandango napi (`fandango.com/napi/theaterMovieShowtimes`) | Exact showtimes + formats (IMAX/RPX), via plain httpx; **off by default** |

"Off by default" theaters are scraped and available, but their filter chip starts unchecked —
readers click it to add them. **Regal** reads from **Fandango** (one JSON call per date, no
browser) because Regal's own site is Cloudflare-gated and only server-renders the current day —
Regal sells tickets through Fandango, whose `napi` endpoints are open (see `scrapers/fandango.py`).

## Quick start (local)

```bash
python -m venv .venv
.venv\Scripts\activate              # Windows;  source .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
python -m playwright install chromium

python -m movie_scraper --dry-run   # preview what would be scraped
python -m movie_scraper             # write public/data.json

python -m http.server 8765 --directory public   # then open http://localhost:8765/
```

Useful flags: `--theater sie|landmark|amc` (repeatable), `--dry-run`, `--output PATH`, `-v`.

## Configuration — `config.toml`

- `timezone`, `days_ahead` (rolling window), `default_runtime_minutes`
- `[theaters.*]` — `enabled` (scrape + include), `default_on` (whether its filter chip starts
  ON; set `false` for secondary venues), display `name`, calendar `color`, and optionally
  `scraper` (reuse another theater's scraper class) + `location` (that scraper's theatre id —
  an AMC slug path, an Alamo venue, or a Fandango theater id)
- `[filters]` (optional) — `title_include` / `title_exclude` (regex), `weekdays`,
  `earliest` / `latest` (local `HH:MM`). Empty = include everything.

## Deploy (GitHub Pages + Actions)

1. Push this repo to GitHub.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. The workflow [`.github/workflows/update.yml`](.github/workflows/update.yml) is **deploy-only**:
   on every push to `main` (and via **Run workflow**) it injects the Pages URL into the Open Graph
   tags and publishes `public/`. It does **not** scrape — see *Updating showtimes* below.

Your calendar will be at `https://<user>.github.io/<repo>/`.

## Updating showtimes

Scraping runs **on your machine**, not in the cloud (AMC blocks GitHub's datacenter IPs; your home
IP works). Showtimes turn over Wed/Thu, so once a week is plenty:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\update.ps1
```

It scrapes the enabled theaters, commits `public/data.json` (and `known_titles.txt`) if they
changed, and pushes — the deploy-only Action republishes. Each run also prints a **new-titles
digest** — the titles that are new since the last run — so you can spot any that need a cleanup
rule in `config.toml` (`[titles]`) before it publishes, instead of re-scanning the whole list.
To automate it, add a weekly Windows Task Scheduler job (adjust the
path):

```powershell
schtasks /create /tn "Denver Showtimes Update" /sc weekly /d THU /st 09:00 ^
  /tr "powershell -ExecutionPolicy Bypass -File C:\Users\CMcGinnis\PythonProjects\movie-scraper\scripts\update.ps1"
```

## Link it from Substack

Paste the Pages URL on its own line in a post and press Enter — Substack renders a preview card
(title, description, and `public/preview.png`). Readers click it to open the live calendar.

## Project layout

```
src/movie_scraper/        scraper package (models, config, pipeline, cli, scrapers/)
public/                   static site (index.html, app.js, styles.css, data.json, preview.png)
tests/                    offline tests + saved fixtures
.github/workflows/        Pages deploy (deploy-only)
scripts/update.ps1        local weekly scrape + push
config.toml               settings
```

## Tests

```bash
pytest                    # runs offline against saved fixtures in tests/fixtures/
```

## Notes & limitations

- All three theaters carry exact showtimes. Landmark's come from a live `schedule` endpoint
  the site calls only after a theater is selected (`from`/`to` cinema-day window +
  `theaters={"id":"X02AK",...}`) — see `src/movie_scraper/scrapers/landmark.py`.
- **AMC** is bot-protected and blocks datacenter IPs, so it can't be scraped from GitHub's runners —
  which is why scraping runs locally (your home IP works). The scraper still supports an `AMC_PROXY`
  env var (a residential proxy) if you ever want AMC scraped from CI, but the local-weekly flow
  doesn't need it.
- The Sie/Eventive request uses Eventive's public publishable read key embedded in their site; if
  it ever rotates, re-extract it (see `src/movie_scraper/scrapers/sie_eventive.py`).
- Scraping is for personal/community convenience — times can change; always confirm on the
  theater's site (every entry links out). Be courteous with run frequency.
```
