# Denver Movie Showtimes — project guide

An interactive web calendar of Denver movie showtimes, built as a companion to Corey
McGinnis's Substack **The Movie Newsletter** (https://coreymcginnis.substack.com/). Readers
filter by film/theater and add any screening to their own calendar (Google / Outlook / .ics).
Live at **https://coreymcginnis1.github.io/denver-showtimes/**, linked from the newsletter.

## Deploy & account rules — IMPORTANT

- This is a **personal** project. Deploy ONLY to the personal GitHub account
  **`coreymcginnis1`** (repo `coreymcginnis1/denver-showtimes`). **Never** push to or use the
  DRCOG/work account **`cmcginnisdrcog`** for this project.
- Both accounts are logged into `gh`. `git push` uses the *active* account's credential, so
  **before any push run `gh auth switch --user coreymcginnis1`** (otherwise it 403s
  "denied to cmcginnisdrcog"). **After pushing, switch back: `gh auth switch --user cmcginnisdrcog`** —
  Corey does concurrent work that needs the work account active.
- Pushing to `main` triggers a **deploy-only** GitHub Action (`.github/workflows/update.yml`)
  that publishes `public/` to GitHub Pages. Non-trivial changes are usually shipped as a **PR on
  the personal account**, reviewed, then merged (merging to `main` deploys).

## How it works

```
scraper (Python, run locally, ~weekly)  →  public/data.json  →  static site (FullCalendar)  →  GitHub Pages
```

- `src/movie_scraper/` — Python package: per-theater scrapers → normalize/filter/dedupe →
  writes `public/data.json`. Run `python -m movie_scraper` (flags: `--theater KEY` repeatable,
  `--dry-run`, `--output`, `-v`). Python 3.11+; deps: httpx, playwright, beautifulsoup4, pydantic.
- `public/` — dependency-free static site (FullCalendar v6 via CDN + vanilla `app.js`). No build.
- **Scraping runs on Corey's machine, not CI** — AMC (and others) block cloud/datacenter IPs; a
  home IP works. Weekly is enough (showtimes turn over Wed/Thu). `scripts/update.ps1` scrapes →
  commits `public/data.json` (+ `known_titles.txt`) if changed → switches the gh account →
  pushes. A Windows Task Scheduler job ("Denver Showtimes Update", Thursdays 9am, run-if-missed)
  runs it weekly.
- `pytest` runs offline against saved fixtures in `tests/fixtures/` (~33 tests).

## Theaters & data sources (`config.toml` `[theaters.*]`)

Seven theaters. The first three are on by default; the rest have `default_on = false` (their
filter chip starts unchecked — opt-in secondary venues). One scraper class can back several
theaters via `scraper` + `location`.

| Theater | Scraper / source |
|---|---|
| Sie FilmCenter | Eventive public API (`api.eventive.org`, embedded publishable key) |
| Landmark Mayan | `landmarktheatres.com` boxofficeapi `schedule` endpoint (httpx) |
| AMC 9+CO 10 | rendered showtimes page via Playwright + DOM parse; `location = denver/amc-9-co-10` |
| AMC Westminster Promenade 24 | same AMC scraper; `location = denver/amc-westminster-promenade-24` (the `denver/` segment is required) |
| Alamo Drafthouse Sloans Lake | `drafthouse.com/s/mother/v2/schedule/venue/sloans-lake` (httpx JSON, no browser) |
| Regal UA Colorado Center / Denver Pavilions | **Fandango** `napi/theaterMovieShowtimes/<id>` (httpx) |

- **Regal quirk (important):** regmovies.com is Cloudflare-gated — it only server-renders the
  *current day* and 403s httpx. Regal sells tickets through **Fandango**, whose `napi` JSON is
  open over plain httpx, so Regal reads from Fandango. `location` is the Fandango theater id
  (**AAFXW** = Colorado Center, **AAJJG** = Denver Pavilions). See `scrapers/fandango.py`.
- **AMC** is bot-protected → why scraping is local. An `AMC_PROXY` env var (residential proxy)
  path exists but isn't used by the local-weekly flow.

## Title normalization (`config.toml` `[titles]`)

Scraped titles are messy (special editions, cuts, anniversary/festival tags, series labels,
sponsor tags, member events, live sports). Three **class-based** regex lists keep the film list
clean as new variants appear each week — prefer *general* patterns over one-offs:

- `strip_prefixes` — series/program labels from the front: "Bleak Week: X" → "X"
  (also Scream Screen, The Popcorn List, Sci-Fi Film Series, Fan Faves, Staff Pick).
- `strip_suffixes` — trailing tags: release year `(2026)`, `Nth Anniversary` (incl. paren form
  `(40th Anniversary)`), `Director's/Extended/... Cut`, `... Edition`, `on 35mm[ film]` (the gauge
  is captured into the format field), `(dir. X)`, Sensory Friendly, sponsor tags (Xfinity),
  Fan Event / Early Access / Promo / Preview screenings, `w/ ...`.
- `drop` — non-films removed entirely: mystery / private-rental / members-only screenings,
  memorial/tribute screenings, watch parties (GOLAZO), live sports (`UFC \d`, Copa Mundial,
  Apple TV Live).

`pipeline.normalize_title()` also title-cases fully UPPER/lowercase titles and down-cases 4+
letter all-caps words (BLEACH→Bleach) so casing variants merge. `Alien` and `Aliens` are
deliberately kept separate (base titles differ; the picks regex uses a `\b` boundary).

**TOML gotcha:** single-quoted TOML strings **cannot contain an apostrophe** (breaks parsing) —
use `\W?` (e.g. `Director\W?s`, not `Director's`) or double quotes for literals without regex
escapes.

## New-titles digest

Each scrape prints titles that are *new since the last run* (tracked in the committed
`known_titles.txt`), so Corey only eyeballs new/odd titles instead of re-scanning the whole
list. See `pipeline.diff_new_titles()`; `update.ps1` commits `known_titles.txt`.

## "Corey's picks" (`config.toml` `[defaults].films`)

Films pre-checked on first load (case-insensitive regex vs the normalized title; empty list =
pre-select all). **Future idea:** auto-generate this allowlist by scraping Corey's Substack
newsletter (RSS) rather than hand-editing.

## Frontend notes (`public/`)

- Warm palette matching the newsletter: `--bg #fffbeb`, `--ink #5c5537`, `--accent #C0432B`
  (warm brick), all WCAG AA. System sans-serif. Per-theater colors are in `config.toml`.
- Views: **Daily** (list; the mobile default), **Week** (grouped by film with theater-color dots
  + time chips), **Month** (one entry per film/day). "Floating time" — the TZ offset is stripped
  so Denver wall-clock shows for every viewer.
- **Mobile:** the filter panel (theater chips + film checklist) collapses behind a "Filters"
  toggle so the calendar is above the fold.
- **Cache-busting:** `index.html` references `styles.css`/`app.js` with `?v=__ASSET_VERSION__`;
  the deploy Action replaces `__ASSET_VERSION__` with the commit SHA so frontend changes show
  immediately. `data.json` is fetched with `cache: "no-store"`. OG tags use a `__SITE_URL__`
  placeholder the Action fills in.

## Substack integration

Substack can't embed interactive widgets, so the calendar is its own Pages site; the newsletter
pastes the URL to get a preview card (OG title/description + `public/preview.png`) readers click
through.
