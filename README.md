# Denver Indie & Repertory Showtimes

An interactive web calendar of movie showtimes for three Denver theaters —
**Sie FilmCenter**, **Landmark Mayan**, and **AMC 9+CO 10** — that readers can filter
by film and from which they can add any screening to their own calendar
(Google / Outlook / Apple `.ics`). Built to be linked from a Substack post.

## How it works

```
scraper (Python)  ──►  public/data.json  ──►  static site (FullCalendar)  ──►  GitHub Pages
   every theater          the data feed         filter + add-to-calendar        daily via Actions
```

- A Python scraper pulls showtimes from each theater and writes `public/data.json`.
- `public/` is a dependency-free static site (FullCalendar + vanilla JS) that renders the feed.
- A scheduled **GitHub Action** re-scrapes daily and deploys `public/` to **GitHub Pages**.
- You paste the Pages URL into Substack; it renders a preview card that readers click through.
  (Substack can't embed interactive widgets inline — only a fixed allowlist — so the calendar
  lives on its own page and Substack links to it.)

## Data sources

| Theater | Source | Detail |
|---|---|---|
| Sie FilmCenter | Eventive public API (`api.eventive.org`) | Exact showtimes |
| AMC 9+CO 10 | Rendered showtimes page (Playwright) | Exact showtimes, ~2 weeks |
| Landmark Mayan | `boxofficeapi` `schedule` endpoint | Exact showtimes, screen + format, direct booking links |

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
- `[theaters.*]` — `enabled`, display `name`, calendar `color`
- `[filters]` (optional) — `title_include` / `title_exclude` (regex), `weekdays`,
  `earliest` / `latest` (local `HH:MM`). Empty = include everything.

## Deploy (GitHub Pages + Actions)

1. Push this repo to GitHub.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. The workflow [`.github/workflows/update.yml`](.github/workflows/update.yml) runs on a daily
   cron, on every push to `main`, and via **Run workflow** (Actions tab). It scrapes, injects the
   Pages URL into the page's Open Graph tags, and deploys `public/`.

Your calendar will be at `https://<user>.github.io/<repo>/`.

## Link it from Substack

Paste the Pages URL on its own line in a post and press Enter — Substack renders a preview card
(title, description, and `public/preview.png`). Readers click it to open the live calendar.

## Project layout

```
src/movie_scraper/        scraper package (models, config, pipeline, cli, scrapers/)
public/                   static site (index.html, app.js, styles.css, data.json, preview.png)
tests/                    offline tests + saved fixtures
.github/workflows/        daily scrape + Pages deploy
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
- **AMC** is bot-protected; rendering usually succeeds, but a run from GitHub's datacenter IPs may
  occasionally be challenged. The pipeline isolates each theater, so one failing still deploys the
  others (and a failed Action emails you).
- The Sie/Eventive request uses Eventive's public publishable read key embedded in their site; if
  it ever rotates, re-extract it (see `src/movie_scraper/scrapers/sie_eventive.py`).
- Scraping is for personal/community convenience — times can change; always confirm on the
  theater's site (every entry links out). Be courteous with run frequency.
```
