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
- **Nothing piles up:** each run rebuilds `data.json` for today … +14 days (Sie, Landmark and Alamo
  to +90, ~350 more showings); `openings` forget films
  400 days after they last opened; `film_meta`/`tmdb_ids` hold only current films. Events carry only
  the fields the site reads (no nulls), and each poster URL only on a film's first showing
  (`_build_feed`; the page gathers posters per film), so with 32 theaters (~10,400 showings) a daily
  data commit is ~6.2 MB raw, ~775 KB as served (gzip). Most of what's left is Fandango ticket
  links (a unique hash each). Git history grows ~60–200 MB/year; don't rewrite history to trim it.

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
  - `scrapers/` — `sie_eventive.py`, `landmark.py`, `alamo.py`, `fandango.py` (AMC/Regal/Harkins/
    Cinemark/Emagine/Movie Tavern), `dairy.py` (Dairy Arts Center), `cu_ifs.py` (CU Film Series).
  - `pipeline.py` — cleanup, TMDB standardization, openings, trending, feed, run summary.
  - `tmdb.py` · `wikipedia.py` · `omdb.py` (off) · `formats.py` · `config.py` · `cli.py` · `models.py`.
- `public/` — `index.html`, `styles.css`, `app.js` (vanilla, no build), `zips.json`,
  `tmdb-logo.svg`, `favicon.svg` (brick square, white D), `preview.png` (Substack card, 1200×630, the
  redesign's look; regenerate if the masthead or theaters change), `data.json` (written by the workflow).
- `config.toml` — theaters, cleanup rules, TMDB overrides, feature switches.
- `tests/` — offline, against saved fixtures in `tests/fixtures/`.

### `data.json`

`theaters` (key, name, color, default_on, lat, lon, optional `site`) · `films` · `events` (`id`, `title`, `start`,
optional `end`/`allDay`, `extendedProps`: `theater`, `screen`, `fmt`, `ticketUrl`, `poster`,
`lang`, `rating`, `runtime`, `year`, `release`) · `film_meta` (displayed title → TMDB data:
`directors`, `cast` (top five billed), `genres`, `countries`, `overview`, `trend`, `wiki_views`, …) · `tmdb_ids` (local title → TMDB id) · `openings` (title → Denver opening date) ·
`stale_theaters` · `generated_at` · `timezone`.

## Theaters (`config.toml` `[theaters.*]`)

Thirty-two theaters: **every year-round theater within 30 mi of 80218** (checked on Fandango Nov
2026; Longmont's Regal sits right on the line), plus Boulder's two film venues, so readers anywhere in
the metro can find the ones nearest them. Sie and Landmark Mayan start on; the rest have
`default_on = false`. One scraper can back several theaters via `scraper` +
`location`. `lat`/`lon` drive the distance filter.

| Theater | Source |
|---|---|
| Sie FilmCenter | Eventive public API (`api.eventive.org`, embedded publishable key) |
| Landmark Mayan / Greenwood Village | landmarktheatres.com boxofficeapi `schedule` endpoint; `location` X02AK / X0873 |
| AMC 9+CO 10 / Westminster Promenade 24 | **Fandango** `napi/theaterMovieShowtimes/<id>`; AAYUA / AAECN |
| Regal UA Denver Pavilions / Colorado Center | **Fandango**; AAJJG / AAFXW |
| Harkins Arvada 14 / Northfield 18 | **Fandango**; AAYFG / AATYG |
| AMC Dine-In Cherry Creek 8 / Bowles Crossing 12 / Highlands Ranch 24 / Arapahoe Crossing 16 | **Fandango**; AAADR / AABAT / AAECM / AAEWN |
| Regal River Point / SouthGlenn / UA Colorado Mills | **Fandango**; AAVKZ / AAVRY / AAQQK |
| Cinemark Century Bel Mar 16 and XD / Century Aurora and XD | **Fandango**; AARMQ / AAJNI |
| Movie Tavern Aurora (Marcus) | **Fandango**; AAUFX |
| AMC Orchard 12 / Flatiron Crossing 14 / Southlands 16 / Showplace Brighton 12 / Castle Rock 12 | **Fandango**; AAUUN / AAQBW / AATXU / AATIQ / AATTI |
| Emagine Parker · Cinemark Century Boulder · Regal Village at the Peaks (Longmont) | **Fandango**; AAQPS · AAUNI · AAHTU |
| Dairy Arts Center, Boulder (Boedecker + Gordon Gamm Theaters) | thedairy.org's The Events Calendar REST API, `/wp-json/tribe/events/v1/events?categories=cinema` (one ranged request, 90-day look-ahead; skips Cinema Club talks and youth board meetings by tag; strips the run dates from titles, "Queen at Sea \| Nov. 11 – 14") |
| International Film Series (CU Boulder), Muenzinger Auditorium | CU's Localist calendar API, `calendar.colorado.edu/api/2/events?group_id=13934` (Film-type events only, 90-day look-ahead, 1 s between pages per robots.txt). internationalfilmseries.com refuses automated requests (403, robots.txt included), so it isn't touched; links go there. Most but maybe not all IFS films reach the campus calendar. |
| Alamo Drafthouse Sloans Lake / Westminster / Littleton | `drafthouse.com/s/mother/v2/schedule/venue/<location>` (JSON, one request each, whole schedule); `sloans-lake` / `westminster` / `littleton` |

- **AMC, Regal, Harkins, Cinemark and Movie Tavern come from Fandango:** amctheatres.com and
  regmovies.com block scrapers (Cloudflare / bot challenges); Fandango's `napi` JSON is open over
  plain httpx, and its ticket links work. One request per theater per day (~0.3 s each), so the ten
  added in Nov 2026 cost under a minute a run. Fandango silently serves a grey "F" placeholder image
  when it lacks a poster.
- **Coverage (Nov 2026):** Fandango's `napi/theaterswithshowtimes?zipCode=` / `napi/nearbyTheaters`
  return only the nearest 21 per zip, so the lists were built from 80218 plus rings of suburban zips
  out to 36 mi. Within 30 mi nothing on Fandango is left out. Boulder's Dairy blocks AI crawlers
  (GPTBot, ClaudeBot) by name in robots.txt; our scraper identifies itself as `denver-showtimes-bot`
  with the site's address (`base.USER_AGENT`), and its terms say nothing about automated access.
  Radius map: claude.ai artifact "80218 Theater Radius". Not on Fandango: the 88 Drive-In
  (Commerce City, seasonal, first-run double features; would need its own scraper) and summer-only
  series (Elitch Theatre, Sunset Cinema, the Bug's occasional nights). Closed: the Esquire (July
  2024), Chez Artiste (Aug 2024), Denver Mart Drive-In (2021). The ten chains added Nov 2026 mostly
  repeat films playing nearer in, but brought ~21 films found nowhere else (Fathom-style repertory:
  Goldfinger, Scarface, Miami Vice…) and three more IMAX screens (Colorado Mills, Highlands Ranch,
  Arapahoe Crossing).
- **Regal Colorado Center** shrank from ~20 films / ~430 showtimes (July) to ~5–6 / ~115 (Nov 2026)
  while the feed stayed healthy, so the theater itself is running fewer screens. If it drops to
  zero, check regmovies.com in a browser before treating it as a scraper failure.

## Titles

### Cleanup rules (`config.toml` `[titles]`, mirrored in `config.py` `DEFAULT_*` — keep in sync)

Prefer **general** patterns over one-offs.

- `strip_prefixes` — series/presenter labels: Bleak Week, Scream Screen, The Popcorn List, Sci-Fi
  Film Series, Fan Faves, Staff Pick, Crunchyroll Anime Nights, Sie's "… Dose of Reality
  [Screening]", any "<Presenter> Presents:", the Dairy's Friday Night Weird and Cinema Classics
  (with Jeffrey Kash), CU's "Film Screening:".
- `strip_suffixes` — release year `(2026)`, `Nth Anniversary` (paren/colon forms), `… Cut`,
  `… Edition`, `Re-release`/`Reissue`/`(RE26)`, `Encore`/`(2026 Encore)`, language versions
  (`(English 2026)`, `(Hindi Dubbed)`), `on 35mm` (gauge kept as the format), `(dir. X)`, Sensory
  Friendly, sponsor tags, Fan Event / Early Access / Promo / Preview screenings, `- Super Ticket`
  (ticket bundles), `w/ …`, CU's `- Part of <festival>`, `- FREE SHOW`, `- <guests> in person!`,
  `- IFS Underground`; `(Director's Cut)` in parentheses too.
- `drop` — not films: mystery screenings (Screen Unseen, Mystery Movie, Harkins Secret Cinema,
  Cinemark Secret Movie Series, a bare "IFS Underground"),
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
  Matches are remembered in `tmdb_ids`. `0` means "not on TMDB" (an event sharing a film's name:
  the Dairy's "Family Reunion" shorts night). `"Title @theater"` scopes an override to one theater
  when two show different films under one title (`"Little Women @dairy"` = the 1933 one, while the
  Alamos show 2019's); the two then read "Little Women (1933)" / "(2019)".
- **Special events = no TMDB movie match:** TV episodes (Heated Rivalry), double features, shorts
  programs, one-night events. The site tags them "Special event", sorts them last (their own
  section under Show All), leaves them out of New releases / Repertory, and gives them no "new" tag. A real film missing from TMDB lands here too — fix with
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

Redesigned again Nov 2026 to look less generic ("less AI-built"; Corey prefers character over polish):
a printed listings page, not an app. Near-white paper `--paper #f7f5f0`, black ink, newsletter brick
`--brick #b83a22` as the one accent. **One typeface, Archivo** (variable weight + width): condensed **caps only for the masthead
and section heads**; film titles bold condensed in their own capitalization (readability); big
condensed day and hour numerals. Modern, not a newspaper pastiche, **self-hosted** in
`public/fonts/` (latin + latin-ext woff2, OFL alongside) so no visit reports to Google. Heavy black
rules instead of boxes; no pills, dots, count badges, shadows or "·" separators. Posters keep 3px
corners. Corey kept the original Show / Sort toggles (small caps labels, 4px selected tint): clean
and familiar beats strict consistency there. Mockups: claude.ai canvas "Denver Showtimes
redesign directions" (A listings + C program won; B marquee rejected).

- **Controls:** masthead "Denver Movie Showtimes" with the chosen date under it · sticky day strip
  ("All dates", then the weekday, never "Today", "Nov" over a big "10" over "Tue", like a tear-off calendar, every day the same width; the selected day is a brick block) · **Theaters**:
  "Theaters near [zip] within 1 mi / 3 mi / 5 mi / any distance" (no 10 mi on purpose: past
  5 mi, readers pick a specific theater by name) and a checklist of all 32 nearest first
  with miles in one row that scrolls sideways: no scrollbar, the side with more fades and gets a ‹ / ›
  arrow (no counts, no theater colors). **Phones** fold theaters *and* Show/Sort into one line, "At Sie
  and Mayan, all films, newest first · Change", with search under it; opened, the checklist runs top
  to bottom with the 5 nearest plus any checked (`TK_SHOWN`, picked on open / zip / distance, not per
  tap) and "Show all 32 theaters" / "Show fewer theaters", so Show / Sort stay close. Hover colors
  only apply under `(hover: hover)` (a tap leaves :hover stuck on phones). The masthead is one line and
  the date line is dropped (the brick day says it), so posters start in the first screen. Zip default
  **80218**, **never saved**; straight-line distance from Census zip centroids in `zips.json`. Theater
  choices are saved in `localStorage` with the default set they were made against (changing `default_on`
  resets everyone) · "Find a film" search first (× clears it; Enter closes the phone keyboard), then
  **Show** All / New releases / Repertory / **On film** and **Sort** Newest / Trending / A–Z. On film (Corey's
  interest) keeps only showings projected from a print (16/35/70mm, IMAX 70mm, VistaVision). It's a
  plain filter like the other Show choices: the chosen day and theaters only; **All dates** lists every
  print coming up (Now playing / Coming soon / Further out), and a day with none says "Nothing on film
  at these theaters on this day. Try All dates or more theaters." (Its own "On film on other dates /
  at other theaters" sections were dropped Nov 2026 as clutter.)
  **Look-ahead** (`ahead_days = 90`, `fetch_ahead()`): sources that can look months out cheaply (Sie,
  one request a week; Landmark, one ranged request; the three Alamos, their full feeds; the Dairy and
  CU's calendar, one ranged request each) report **everything** up to 90
  days; Fandango (a request per day per theater) stops at 14. The day strip stays at `WINDOW_DAYS` = 14;
  later dates show only in All dates ("Further out") and search.
  - **Newest:** new releases by Denver **release week** (Friday–Thursday; Wed/Thu previews count
    toward the Friday they lead into, `releaseWeek()`), latest and upcoming first, **Trending within
    a week**; then repertory by original release; special events last. With Show **All** (any sort),
    a day always splits into **New releases / Repertory / Special events**, each in the chosen sort. Films without the data sort last.
- **Cards:** poster, "Opening week" (first 7 days in Denver) / "Opens Nov 19", the title (bold condensed, its own capitalization),
  then times by theater (nearest first, like the checklist) as plain text ("11:50 am 1:45 pm 4:30 pm", every time with its am/pm;
  a format all of a theater's showings share goes on the theater line, "Alamo, 35mm"). **Tap the
  poster or the title** for the details over the poster (no "i" mark: a pointer, and on hover the poster
  dims and the title underlines): director(s), country (non-US), year, runtime, rating, TMDB synopsis,
  Letterboxd link (`film_meta.directors` / `.countries` / `.overview`, from the same TMDB request with
  `append_to_response=credits`). Special events have no details, so their poster isn't a button.
  **Posters:** TMDB `w500` first, other theaters' art next, Fandango (600 px renderer) last, then the
  title set white on black. Long lists clamp at 210px behind "Show all times" / "Show all N theaters"
  (`clampVenues()`), only when that hides 90px or more (`CLAMP_SLACK`): hiding a line or two made
  the card *shrink* on expand (the button went, a few px came in). Every "Show all" toggles to
  "Show fewer …", and collapsing keeps the button where it was on screen (`toggleMore()`).
- **Schedule:** the day in time order under big brick hour numerals, each with its am/pm (earlier-today rows behind a
  button). Desktop: sticky right column that scrolls on its own with **no scrollbar**, like the
  theater row: the end with more fades out (`schedEdges()`). Phone: Films / Schedule tabs.
- **All dates:** **Now playing** (a showing today at the selected theaters, or a new release already open in Denver whose next showing is within `RUN_GAP_DAYS` = 3 days; repertory and events need today; by the chosen sort) then **Coming soon** (everything else, repertory included, by its next showing); each
  theater gets one line with its next showing ("Alamo Sat Nov 7, 5:00 pm through Nov 11"), soonest first; three show, the rest behind "Show all N theaters" (`SPAN_SHOWN`). Then **Further out**: films whose first showing is past the two weeks, soonest first, with the note "Sie, Landmark, Alamo, Dairy and CU Film Series only." Search's extra matches ("Playing on other dates" / "Playing at other theaters") work the same way. No schedule column.
- **Formats and languages** (`formats.py`, shared by every scraper; Corey's rule, Nov 2026): only
  formats people pick a showing for are named — **IMAX, IMAX 3D, IMAX 70mm, Dolby (Cinema), Dolby 3D,
  3D, 16mm, 35mm, 70mm, VistaVision**. Every other premium screen (AMC Prime, RPX, 4DX, ScreenX, Harkins
  Ciné XL…) is theater branding, so it's just **PLF** (premium large format); 3D in one of those is
  plain "3D". Laser projection, Atmos sound, seating and aspect ratios (Landmark's Scope / Flat) aren't
  formats. Fandango's header says only Standard / Premium Format / 3D, so the screen comes from the
  showtime group's amenities. **Language** (`lang`): "Subtitled", "Dubbed", or "<Language> dub"
  ("Spanish dub"), from Fandango amenities, Alamo attributes and the Sie's `subtitle_language` (non-English
  film + English subtitle track = Subtitled). Harkins says only "Japanese Language": the scraper passes
  "Japanese language" and the page (`resolveLang()`) compares it with TMDB's original language:
  same = Subtitled, an English film = "<X> dub", anything else = "In <X>". Sources only flag the
  exceptions (Alamo flags nothing), so an untagged showing of a foreign film can be either. Sie's prints come from the title ("… on 35mm",
  "… in VistaVision") or a "35mm" Eventive tag (Eventive has no projection field). On the site, a format/language all of a theater's showings share goes on the
  theater line ("Regal Pavilions, Subtitled"); mixed ones get a short red mark per time (`FMT_TAG`:
  IMAX, Dolby, 3D, PLF, Sub, Dub…, else the label itself). Format and language are judged
  **separately** (`shared()` / `ownTag()`): all-subtitled showings with a few PLF ones read "Regal
  Pavilions, Subtitled" with "PLF" only on those times.
- **Search** ("Title, director, actor or genre"; `hitOf()`): a title matches anywhere; from three
  letters on, so does the start of a word in a director's or top-five-billed actor's name or a TMDB
  genre (`film_meta.directors` / `.cast` / `.genres`, all from the one TMDB request; "sci-fi" finds
  Science Fiction, "animated" Animation). Accents and capitals don't matter ("almodovar"). A card
  found by anything but its title says why under the title ("Directed by Pedro Almodóvar", "With
  Pedro Pascal", "Horror"), or the match looks like a mistake. Search also shows matches beyond the
  selected day and theaters, split into "Playing on other dates" (your theaters) and "Playing at
  other theaters" (e.g. Fjord, only at AMC Westminster).
- **Tap a time** → sheet with Get tickets and one "Add to calendar" button that opens Google, Outlook,
  Apple/.ics (ICS uses TZID America/Denver). Fandango showings read "Get tickets on Fandango" (straight to
  the seats) with "Or buy from AMC directly" under it: the theater's own page (`site` in config.toml;
  skips Fandango's fee and earns the chain's rewards, but the reader picks the time again, as Fandango's
  data has no chain showtime ids). AMC and Regal block automated checks, so their pages came from search
  results; where none confirmed a theater's page (seven AMCs, Regal River Point, Harkins' JavaScript-only
  site) `site` is the chain's Denver / theater list. Swap in the real page when one is confirmed.
- **Times read "3:00 pm"** (lowercase, no periods; `hm12()`); digits tabular, "am/pm" in `.ap`.
- "Floating time": the ISO offset is ignored, so every viewer sees Denver wall-clock times; "now"
  (for dimming past showtimes) is computed in America/Denver. A tab left open overnight reloads when
  it comes back on a new Denver date (`visibilitychange`).
- **Notice** (`renderNotice()`): silent normally. If the update is over 36 h old: "Showtimes were last
  updated <day>…"; otherwise, if a selected theater is in `stale_theaters`: "Couldn't refresh <theater>
  today; its times are from the last update."
- **Privacy:** no cookies, no analytics. The only browser storage is the theater pick
  (`dst-theaters` in `localStorage`, never sent anywhere); the zip is never saved. Third-party
  requests are poster images only (TMDB, Fandango, theaters). Keep it that way.
- **Footer** credits TMDB (logo + required notice; posters, directors and synopses) and Wikipedia, and links each theater company's site (one link per company; Movie Tavern goes to marcustheatres.com, as movietavern.com's certificate had lapsed in Nov 2026).
- **Cache-busting:** `index.html` loads `styles.css`/`app.js` with `?v=__ASSET_VERSION__`, replaced
  with the commit SHA on deploy; `data.json` is fetched `no-store`. OG tags use `__SITE_URL__`.

## Substack

Substack can't embed interactive widgets, so the site stands alone; the newsletter pastes the URL
for a preview card (OG title/description + `public/preview.png`).

## Next up (Corey's list, Nov 6 2026)

Bigger questions:
- **Cleaner address**: a free `denvershowtimes` GitHub organization (denvershowtimes.github.io),
  with a redirect from the old link so newsletter links keep working.
- **Private code, public site**: Pages from a private repo needs GitHub Pro (~$4/mo). Free route:
  private source repo; the workflow pushes only the built `public/` to a public repo (e.g. the
  org's `denvershowtimes.github.io`) with a deploy token secret. `data.json` stays public either
  way. Also trim the README to a few lines.
