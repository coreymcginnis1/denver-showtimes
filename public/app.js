/* Denver Showtimes: one day at a time, set like a printed listings page.
   Poster cards for every film playing on the chosen day (times grouped by theater; tap a poster for
   the director and synopsis), plus the day's schedule by hour. Tap a time for tickets or to add it to
   Google / Outlook / .ics.
   Times are Denver wall-clock ("floating"): the ISO offset is ignored, so every viewer sees the
   time printed on the theater's own site. No dependencies. */
(function () {
  "use strict";

  // Names for the theater checklist; the full name is used in the sheet and calendar entries.
  var SHORT = { sie: "Sie FilmCenter", landmark: "Landmark Mayan", amc: "AMC 9+CO 10", regal_pavilions: "Regal Pavilions",
    alamo_sloans: "Alamo Sloans Lake", alamo_westminster: "Alamo Westminster", alamo_littleton: "Alamo Littleton",
    regal_colorado: "Regal Colorado Ctr", amc_westminster: "AMC Westminster",
    landmark_greenwood: "Landmark Greenwood Village", harkins_arvada: "Harkins Arvada", harkins_northfield: "Harkins Northfield",
    amc_cherry_creek: "AMC Cherry Creek", cinemark_belmar: "Cinemark Bel Mar", regal_river_point: "Regal River Point",
    cinemark_aurora: "Cinemark Aurora", regal_southglenn: "Regal SouthGlenn", regal_colorado_mills: "Regal Colorado Mills",
    amc_bowles: "AMC Bowles Crossing", amc_highlands_ranch: "AMC Highlands Ranch", movie_tavern_aurora: "Movie Tavern Aurora",
    amc_arapahoe: "AMC Arapahoe Crossing",
    dairy: "Dairy Arts Center", cu_ifs: "CU Film Series", amc_orchard: "AMC Orchard", amc_flatiron: "AMC Flatiron Crossing",
    amc_southlands: "AMC Southlands", emagine_parker: "Emagine Parker", amc_brighton: "AMC Brighton", amc_castle_rock: "AMC Castle Rock",
    cinemark_boulder: "Cinemark Boulder", regal_longmont: "Regal Longmont" };
  var THEATER_SITES = [   // one link per company; each site lists its own locations
    ["Sie FilmCenter", "https://www.denverfilm.org/"],
    ["Landmark", "https://www.landmarktheatres.com/"],
    ["AMC", "https://www.amctheatres.com/"],
    ["Regal", "https://www.regmovies.com/"],
    ["Harkins", "https://www.harkins.com/"],
    ["Cinemark", "https://www.cinemark.com/"],
    ["Alamo Drafthouse", "https://drafthouse.com/denver"],
    ["Movie Tavern", "https://www.marcustheatres.com/"],
    ["Emagine", "https://www.emagine-entertainment.com/"],
    ["Dairy Arts Center", "https://thedairy.org/cinema/"],
    ["CU International Film Series", "https://www.internationalfilmseries.com/"]   // Marcus runs it; movietavern.com's certificate had lapsed (Nov 2026)
  ];
  // Shortest names, for the times under a poster, the hour list and the "At Sie and Mayan" line.
  var TINY = { sie: "Sie", landmark: "Mayan", amc: "AMC 9+CO 10", regal_pavilions: "Regal Pavilions",
    alamo_sloans: "Alamo Sloans Lake", alamo_westminster: "Alamo Westminster", alamo_littleton: "Alamo Littleton",
    regal_colorado: "Regal Colorado", amc_westminster: "AMC Westminster",
    landmark_greenwood: "Landmark Greenwood Village", harkins_arvada: "Harkins Arvada", harkins_northfield: "Harkins Northfield",
    amc_cherry_creek: "AMC Cherry Creek", cinemark_belmar: "Cinemark Bel Mar", regal_river_point: "Regal River Point",
    cinemark_aurora: "Cinemark Aurora", regal_southglenn: "Regal SouthGlenn", regal_colorado_mills: "Regal Colorado Mills",
    amc_bowles: "AMC Bowles Crossing", amc_highlands_ranch: "AMC Highlands Ranch", movie_tavern_aurora: "Movie Tavern Aurora",
    amc_arapahoe: "AMC Arapahoe Crossing",
    dairy: "Dairy Arts Center", cu_ifs: "CU Film Series", amc_orchard: "AMC Orchard", amc_flatiron: "AMC Flatiron Crossing",
    amc_southlands: "AMC Southlands", emagine_parker: "Emagine Parker", amc_brighton: "AMC Brighton", amc_castle_rock: "AMC Castle Rock",
    cinemark_boulder: "Cinemark Boulder", regal_longmont: "Regal Longmont" };
  // Formats and languages (scraper's formats.py): IMAX, Dolby, film prints and 3D by name; every other
  // premium screen is "PLF"; a dub ("Dubbed", "Spanish dub"). A theater whose showings all share one goes
  // on its line; mixed ones get a short red mark per time (anything not listed uses its own name).
  var FMT_TAG = { "IMAX": "IMAX", "IMAX 3D": "IMAX 3D", "IMAX 70mm": "IMAX 70", "Dolby": "Dolby", "Dolby 3D": "Dolby 3D",
    "3D": "3D", "16mm": "16mm", "35mm": "35mm", "70mm": "70mm", "PLF": "PLF", "Premium Format": "PLF", "Dubbed": "Dub" };
  function fmtName(f) { return f === "Premium Format" ? "PLF" : f; }   // older data said "Premium Format"
  function tagOf(s) { return [s.fmt ? fmtName(s.fmt) : "", s.lang || ""].filter(Boolean).join(", "); }   // "IMAX, Spanish dub"
  function shortTag(t) { return t.split(", ").map(function (x) { return FMT_TAG[x] || x; }).join(" "); }
  // Format and language are judged separately for a theater's showings: whatever all of them share
  // goes on the theater line ("AMC, Spanish dub"); only what differs is marked on a time ("2:00 pm PLF").
  // Judged together, one PLF showing used to push a language mark onto every time.
  function shared(list) {
    var same = function (get) { var v = get(list[0]); return list.every(function (s) { return get(s) === v; }) ? v : null; };
    return { fmt: same(function (s) { return s.fmt ? fmtName(s.fmt) : ""; }), lang: same(function (s) { return s.lang || ""; }) };
  }
  function sharedLabel(sh) { return [sh.fmt, sh.lang].filter(Boolean).join(", "); }
  function ownTag(s, sh) {   // what this showing has that its theater's other showings don't all share
    return [sh.fmt == null && s.fmt ? fmtName(s.fmt) : "", sh.lang == null && s.lang ? s.lang : ""].filter(Boolean).join(", ");
  }
  var COUNTRY = (function () { try { return new Intl.DisplayNames(["en"], { type: "region" }); } catch (e) { return null; } })();
  var LANGUAGE = (function () { try { return new Intl.DisplayNames(["en"], { type: "language" }); } catch (e) { return null; } })();
  // A showing "in Japanese" (Harkins says only that) is the subtitled original when the film is
  // Japanese (TMDB's original language), or a dub when it isn't ("Spanish language" on an English film).
  // Per showing, only a dub is marked. The film's own language is said once, "In Spanish", under its
  // title (card and film page), from TMDB's original language. Sources report "Subtitled" unevenly
  // (Alamo's data has no language field at all), so it read "Subtitled" at one theater and not the
  // next for the same print: it's dropped here (Corey, Nov 2026). "Japanese language" (Harkins) in the
  // film's own language says nothing either; on an English film it's a dub.
  function origLang(f) {
    if (!f.olang || f.olang === "xx") return null;   // "xx": no spoken language (silent films)
    if (f.olang === "cn") return "Cantonese";         // TMDB's code for Cantonese
    try { return LANGUAGE ? LANGUAGE.of(f.olang) : null; } catch (e) { return null; }
  }
  function langLine(f) { return f.olang && f.olang !== "en" && origLang(f) ? "In " + origLang(f) : ""; }
  function resolveLang(raw, f) {
    if (!raw || raw === "Subtitled") return null;
    var m = /^(\w+) language$/.exec(raw);
    if (!m) return raw;   // "Dubbed", "Spanish dub"
    var orig = origLang(f);
    var same = orig === m[1] || (orig === "Chinese" && /^(Mandarin|Cantonese)$/.test(m[1]));
    // Only an English film in another language is surely a dub; any other mismatch just says the language.
    return same ? null : f.olang === "en" ? m[1] + " dub" : "In " + m[1];
  }

  var $ = function (id) { return document.getElementById(id); };
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function store(k, v) {   // per-browser conveniences only; the page works without storage
    try { if (v === undefined) return JSON.parse(localStorage.getItem(k)); localStorage.setItem(k, JSON.stringify(v)); }
    catch (e) { return null; }
  }

  // "Now" on a Denver wall clock, so past showtimes dim correctly for viewers anywhere.
  var NOW = (function () {
    var P = {};
    new Intl.DateTimeFormat("en-CA", { timeZone: "America/Denver", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(new Date()).forEach(function (p) { P[p.type] = p.value; });
    return { day: P.year + "-" + P.month + "-" + P.day, hm: (P.hour === "24" ? "00" : P.hour) + ":" + P.minute };
  })();

  var D, films = [], shows = [], days = [], theaters = [];
  // Distances are from the centre of a zip code to each theater, as the crow flies. The zip is
  // never saved: it resets to DEFAULT_ZIP on every visit, so nothing about a reader is kept.
  var DEFAULT_ZIP = "80218", ZIPS = {};   // distance buttons (1 / 3 / 5 mi / All) are in index.html
  var state = { day: null, q: "", sort: "new", kind: "all", showEarlier: false, theaters: null, zip: DEFAULT_ZIP, radius: null,
    film: null, fpDay: null, fpAll: false, fpOpen: {}, fpScroll: 0, fpFromList: false,   // the film page (see "Film page")
    tShown: null, tAll: false };

  // ---- Data ------------------------------------------------------------------

  function load(data) {
    D = data;
    theaters = data.theaters;
    var meta = data.film_meta || {}, index = {};
    films = data.films.map(function (t, i) {
      index[t] = i;
      var m = meta[t] || {};
      return { t: t, id: m.tmdb_id || null, rel: m.release || null, pop: m.popularity, trend: m.trend != null ? m.trend : null, va: m.vote_average, vc: m.vote_count || 0,
        indie: !!m.indie, intl: !!m.intl, olang: m.lang || null, dirs: m.directors || [], countries: m.countries || [], about: m.overview || "",
        cast: m.cast || [], genres: m.genres || [], qt: fold(t), mc: m.metacritic != null ? m.metacritic : null,
        posters: [], tmdbPoster: m.tmdb_poster || null, rating: null, runtime: null, year: m.release ? +m.release.slice(0, 4) : null };
    });
    data.events.forEach(function (e) {
      var f = films[index[e.title]], x = e.extendedProps;
      if (!f) return;
      if (x.poster && f.posters.indexOf(x.poster) < 0) f.posters.push(x.poster);
      if (!f.rating && x.rating && x.rating !== "Not Rated") f.rating = x.rating;
      if (!f.runtime && x.runtime) f.runtime = x.runtime;
      if (!f.year && x.year) f.year = x.year;
      shows.push({ f: index[e.title], th: x.theater, d: e.start.slice(0, 10), hm: e.allDay ? null : e.start.slice(11, 16),
        end: e.end ? e.end.slice(0, 16) : null, fmt: x.fmt, lang: resolveLang(x.lang, f), scr: x.screen, url: x.ticketUrl, id: e.id });
    });
    var openings = data.openings || {};
    films.forEach(function (f, i) {
      // theater art first (Fandango's is the most consistent), then TMDB's
      // TMDB's poster first: official art for every matched film. Fandango silently serves a grey
      // "F" placeholder when it lacks art (it loads fine, so the error fallback never fires), so
      // its images go last; other theaters' art sits in between, mainly for special events.
      f.posters.sort(function (a, b) { return (a.indexOf("fandango") >= 0) - (b.indexOf("fandango") >= 0); });
      if (f.tmdbPoster) f.posters.unshift(f.tmdbPoster);
      // Denver opening: the first day it played at a theater we track (kept by the scraper).
      f.opened = openings[f.t] || shows.filter(function (s) { return s.f === i; })
        .map(function (s) { return s.d; }).sort()[0] || null;
      f.rep = isRepertory(f);
      // A special event: anything TMDB doesn't know as a movie (TV episodes like Heated Rivalry,
      // double features, shorts programs, one-night events). Not a new release or repertory.
      f.event = !f.id;
    });
    // Each film's page address, "#film/wild-horse-nine" (two films with one slug get the TMDB id too).
    films.forEach(function (f, i) {
      var k = slug(f.t);
      if (keyFilm[k] != null) k += "-" + (f.id || i);
      filmKey[i] = k; keyFilm[k] = i;
    });
    shows.forEach(function (s) { if (!THEATER_END[s.th] || s.d > THEATER_END[s.th]) THEATER_END[s.th] = s.d; });
    // Each theater's posting edge: the most common last date, after today, among the films it's showing
    // now (most theaters post a week at a time, so most of their current films stop on the same day).
    var runs = {}, ends = {};
    shows.forEach(function (s) {
      var r = runs[s.th + "|" + s.f] || (runs[s.th + "|" + s.f] = { th: s.th, a: s.d, z: s.d });
      if (s.d < r.a) r.a = s.d; if (s.d > r.z) r.z = s.d;
    });
    // Judged per chain (one AMC posts like the next; the Mayan alone has two films), and only where at
    // least POSTED_MIN current films stop on that date: with two films the Dairy's "most common last
    // date" was just Queen at Sea's real last day. The Dairy and CU list each film's whole run up front.
    Object.keys(runs).forEach(function (k) {
      var r = runs[k], g = chainKey(r.th); if (r.a > NOW.day || r.z <= NOW.day || WHOLE_RUNS[g]) return;
      var e = ends[g] || (ends[g] = {}); e[r.z] = (e[r.z] || 0) + 1;
    });
    Object.keys(ends).forEach(function (g) {
      var top = Object.keys(ends[g]).sort(function (a, b) { return ends[g][b] - ends[g][a] || a.localeCompare(b); })[0];
      if (ends[g][top] >= POSTED_MIN) POSTED[g] = top;
    });
    days = Array.from(new Set(shows.map(function (s) { return s.d; }))).sort()
      .filter(function (d) { return d >= NOW.day && dayDiff(NOW.day, d) <= WINDOW_DAYS; });   // later dates: All dates only
    if (!days.length) days = Array.from(new Set(shows.map(function (s) { return s.d; }))).sort();
    state.day = days.indexOf(NOW.day) >= 0 ? NOW.day : days[0];

    // A saved choice holds only while the defaults it was made against are unchanged: when the
    // default theaters change, every reader starts from the new defaults again.
    var defaults = theaters.filter(function (t) { return t.default_on !== false; }).map(function (t) { return t.key; });
    DEFAULTS_SIG = defaults.join(",");
    var saved = store("dst-theaters");
    var valid = saved && saved.d === DEFAULTS_SIG && Array.isArray(saved.on) ? saved.on.filter(function (k) { return theaterOf(k); }) : [];
    state.theaters = new Set(valid.length ? valid : defaults);
  }

  // Repertory: the film first came out more than two years before it opened here (a revival).
  // Two years, not one: indie films often reach Denver a year or more after a festival premiere
  // (TMDB dates them by it). New releases (and events with no release date) are everything else.
  var REPERTORY_DAYS = 730;
  var RUN_GAP_DAYS = 3;     // a new release off today but back within this many days is still "Now playing"
  var SPAN_SHOWN = 3;       // All dates / search: theaters listed before "Show all N theaters"
  var TK_SHOWN = 5;         // phones: theaters in the opened checklist before "Show all 32 theaters"
  var TK_CHECKED = 3;       // ... plus up to this many checked theaters further out
  var CLAMP_PX = 210;       // a card's times stop here (styles.css .venues.clamp) ...
  var CLAMP_SLACK = 90;     // ... but only when that hides this much more: never a button for a line or two
  var WINDOW_DAYS = 14;     // the day strip: today + 14 (Sie, Landmark and Alamo list up to ~90 days out)
  var FURTHER_NOTE = "Select theaters only.";
  function isRepertory(f) {
    var orig = f.rel || (f.year ? f.year + "-07-01" : null);
    return !!(orig && f.opened && dayDiff(orig, f.opened) > REPERTORY_DAYS);
  }

  function miles(t) {
    var z = ZIPS[state.zip];
    if (!z || t.lat == null || t.lon == null) return null;
    var R = 3958.8, r = Math.PI / 180, dLa = (t.lat - z[0]) * r, dLo = (t.lon - z[1]) * r;
    var h = Math.pow(Math.sin(dLa / 2), 2) + Math.cos(z[0] * r) * Math.cos(t.lat * r) * Math.pow(Math.sin(dLo / 2), 2);
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  // Choosing a distance turns on exactly the theaters within it ("All" turns them all on).
  var DEFAULTS_SIG = "";
  function saveTheaters() { store("dst-theaters", { d: DEFAULTS_SIG, on: Array.from(state.theaters) }); }

  function applyRadius() {
    if (state.radius == null) return;
    state.theaters = new Set(theaters.filter(function (t) {
      var mi = miles(t); return state.radius === "all" || (mi != null && mi <= +state.radius);
    }).map(function (t) { return t.key; }));
  }

  // Theaters schedule Friday to Thursday. Wednesday/Thursday previews belong to the Friday they
  // lead into, so shift two days forward, then step back to that week's Friday.
  function releaseWeek(d) {
    var o = new Date(d + "T12:00:00"); o.setDate(o.getDate() + 2);
    o.setDate(o.getDate() - ((o.getDay() + 2) % 7));   // getDay: Fri=5 -> back 0 days
    return o.getFullYear() + "-" + String(o.getMonth() + 1).padStart(2, "0") + "-" + String(o.getDate()).padStart(2, "0");
  }

  function theaterOf(k) { for (var i = 0; i < theaters.length; i++) if (theaters[i].key === k) return theaters[i]; return null; }
  function tName(k) { return SHORT[k] || (theaterOf(k) || {}).name || k; }
  function isPast(s) { return s.d === NOW.day && s.hm && s.hm < NOW.hm; }
  // "On film": projected from a print (16/35/70mm, IMAX 70mm, VistaVision). A filter on showings,
  // not films: a film's digital showings drop out.
  function onFilm(s) { return /^(16|35|70)mm$|^IMAX 70mm$|^VistaVision$/.test(s.fmt || ""); }
  function kindOk(s) {
    var f = films[s.f];
    return state.kind === "all" || (state.kind === "film" ? onFilm(s) : !f.event && (state.kind === "rep") === f.rep);
  }
  // "Find a film" matches a title anywhere ("wild" finds Wild Horse Nine), and from three letters on
  // also the start of a word in a director's or top-billed actor's name, or a genre ("lynch",
  // "pedro pascal", "horror", "sci-fi"). Accents and capitals don't matter ("almodovar").
  function fold(t) { return (t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase(); }
  var GENRE_ALSO = { "Science Fiction": "sci-fi scifi", "Animation": "animated" };
  var hits = { q: null, by: [] };
  function hitOf(i) {   // null, or { why } with why "" for a title match, else "Directed by ..." etc.
    var q = fold(state.q);
    if (hits.q !== q) hits = { q: q, by: [] };
    if (hits.by[i] !== undefined) return hits.by[i];
    var f = films[i], out = null;
    if (!q || f.qt.indexOf(q) >= 0) out = { why: "" };
    else if (q.length >= 3) {
      var re = new RegExp("(^|[\\s'.-])" + q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
      var find = function (list, also) {
        for (var n = 0; n < list.length; n++) if (re.test(fold(list[n]) + (also && also[list[n]] ? " " + also[list[n]] : ""))) return list[n];
        return null;
      };
      var d = find(f.dirs), c = !d && find(f.cast), g = !d && !c && find(f.genres, GENRE_ALSO);
      if (d) out = { why: "Directed by " + d };
      else if (c) out = { why: "With " + c };
      else if (g) out = { why: g };
    }
    return (hits.by[i] = out);
  }
  function dayShows(d, anyTheater) {
    return shows.filter(function (s) {
      return (d === ALL ? s.d >= days[0] && !isPast(s) : s.d === d) && (anyTheater || state.theaters.has(s.th)) && (!state.q || hitOf(s.f)) &&
        kindOk(s);
    });
  }

  // ---- Formatting ------------------------------------------------------------

  function dateObj(d) { return new Date(d + "T12:00:00"); }
  // Every showtime reads "h:mm am" / "h:mm pm" (Corey's house style), e.g. "3:00 pm".
  function hm12(hm) { var h = +hm.slice(0, 2); return ((h % 12) || 12) + ":" + hm.slice(3) + " " + (h < 12 ? "am" : "pm"); }
  var longTime = hm12;   // plain text, for labels and calendar entries
  // On screen the digits stay tabular (so times line up) but "am"/"pm" uses normal figures.
  function timeHTML(hm) { var t = hm12(hm), i = t.indexOf(" "); return t.slice(0, i) + ' <span class="ap">' + t.slice(i + 1) + "</span>"; }
  function longDate(d) { return dateObj(d).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" }); }
  function relDay(d) {
    if (d === ALL) return null;
    var i = days.indexOf(d), t = days.indexOf(NOW.day);
    if (t < 0) return null;
    return i === t ? "Today" : i === t + 1 && dayDiff(NOW.day, d) === 1 ? "Tomorrow" : null;
  }
  function dayDiff(a, b) { return Math.round((dateObj(b) - dateObj(a)) / 864e5); }
  function runtime(m) { if (!m) return ""; var h = Math.floor(m / 60), r = m % 60; return (h ? h + "h " : "") + (r ? r + "m" : ""); }


  // ---- Controls ----------------------------------------------------------------

  function renderSources() {
    $("srcLinks").innerHTML = "Theater sites: " + THEATER_SITES.map(function (t) {
      return '<a href="' + t[1] + '" target="_blank" rel="noopener">' + esc(t[0]) + "</a>";
    }).join(", ");
  }

  var ALL = "all";   // state.day for the "All dates" view
  function shortDate(d) { return dateObj(d).toLocaleDateString("en-US", { month: "short", day: "numeric" }); }

  // A day as a tear-off calendar page: "Nov" over a big "12" over "Thu".
  function dayFace(d) {
    var o = dateObj(d);
    return '<span class="dm">' + o.toLocaleDateString("en-US", { month: "short" }) + '</span><span class="dn">' + o.getDate() +
      '</span><span class="dw">' + o.toLocaleDateString("en-US", { weekday: "short" }) + "</span>";
  }
  function renderDays() {
    $("days").innerHTML = '<button type="button" class="day" data-d="' + ALL + '" aria-pressed="' + (state.day === ALL) + '">' +
      '<span class="dm">&nbsp;</span><span class="dn">All</span><span class="dw">dates</span></button>' + days.map(function (d, n) {
      var rel = relDay(d);
      // Like a tear-off calendar: "Nov" over a big "10" over "Tue". Always the weekday, never "Today",
      // so every day keeps the same width; the month on every day reads right across Nov into Dec.
      return '<button type="button" class="day" data-d="' + d + '" aria-pressed="' + (d === state.day) + '" aria-label="' + (rel ? rel + ", " : "") + longDate(d) + '">' +
        dayFace(d) + "</button>";
    }).join("");
    $("when").textContent = state.day === ALL ? "All dates, from " + shortDate(days[0])
      : longDate(state.day);
  }

  // The theater row hides its scrollbar: fade the side with more theaters and show an arrow there.
  function edges() {
    var l = $("tlist"), max = l.scrollWidth - l.clientWidth, row = $("trow");
    var left = l.scrollLeft > 2, right = max - l.scrollLeft > 2 && getComputedStyle(l).display === "flex";
    row.classList.toggle("more-l", left); row.classList.toggle("more-r", right);
    $("tPrev").hidden = !left; $("tNext").hidden = !right;
  }

  // Phones list the theaters top to bottom: the nearest few and a few checked ones, the rest
  // behind "Show all 32 theaters" so Show / Sort aren't a long scroll away. Picked when the list
  // opens or the zip / distance changes, not on each tap, so a row never vanishes as it's unchecked.
  function pickShownTheaters() {
    var near = theaters.slice().sort(function (a, b) { return (miles(a) || 0) - (miles(b) || 0); });
    // Checked theaters further out stay in the short list too, but only a few ("any distance" checks
    // all 32, which kept the list from ever getting shorter).
    var far = near.filter(function (t, n) { return n >= TK_SHOWN && state.theaters.has(t.key); });
    var keep = near.slice(0, TK_SHOWN).concat(far.length <= TK_CHECKED ? far : []);
    state.tShown = new Set(keep.map(function (t) { return t.key; }));
  }

  function renderTheaters() {
    var near = theaters.slice().sort(function (a, b) { return (miles(a) || 0) - (miles(b) || 0); });
    if (!state.tShown) pickShownTheaters();
    var hidden = near.filter(function (t) { return !state.tShown.has(t.key); }).length;
    $("tlist").innerHTML = near.map(function (t) {
      var mi = miles(t);
      return '<button type="button" class="tk' + (state.tShown.has(t.key) ? "" : " extra") + '" data-k="' + t.key + '" aria-pressed="' + state.theaters.has(t.key) + '">' +
        '<span class="box" aria-hidden="true"></span><span><span class="nm">' + esc(tName(t.key)) + "</span>" +
        (mi != null ? '<span class="mi">' + mi.toFixed(1) + " mi</span>" : "") + "</span></button>";
    }).join("");
    $("tpanel").classList.toggle("all-th", state.tAll);
    var more = $("tMore"); more.hidden = !hidden && !state.tAll;
    more.textContent = state.tAll ? "Show fewer theaters" : "Show all " + near.length + " theaters"; more.setAttribute("aria-expanded", state.tAll);
    document.querySelectorAll("[data-r]").forEach(function (x) { x.setAttribute("aria-pressed", String(x.dataset.r === String(state.radius))); });
    var on = near.filter(function (t) { return state.theaters.has(t.key); }).map(function (t) { return TINY[t.key] || t.name; });
    edges();
    $("tsum").textContent = (!on.length ? "No theaters picked" : on.length <= 2 ? "At " + on.join(" and ") : "At " + on.length + " theaters") + ",";
    renderSummary(); renderNotice();
  }

  // Says something only when something's wrong: a selected theater didn't refresh (the scraper kept
  // its last good rows: data.stale_theaters), or the whole update is over a day and a half old
  // (the daily run normally lands by mid-morning).
  var STALE_HOURS = 36;
  function renderNotice() {
    var msg = "", made = Date.parse(D.generated_at || "");
    var stale = (D.stale_theaters || []).filter(function (k) { return state.theaters.has(k); }).map(tName);
    if (made && (Date.now() - made) / 36e5 > STALE_HOURS)   // the whole update is old: that's the news
      msg = "Showtimes were last updated " + new Date(made).toLocaleDateString("en-US",
        { timeZone: "America/Denver", weekday: "long", month: "long", day: "numeric" }) + ". Check the theater\u2019s site before you go.";
    else if (stale.length)
      msg = "Couldn\u2019t refresh " + listOf(stale) + " today; " + (stale.length > 1 ? "their" : "its") + " times are from the last update.";
    $("notice").textContent = msg;
    $("notice").hidden = !msg;
  }
  function listOf(a) { return a.length < 3 ? a.join(" and ") : a.slice(0, -1).join(", ") + " and " + a[a.length - 1]; }

  // Phones fold the controls to one line: "At Sie and Mayan, all films, newest first · Change".
  var KIND_SUM = { all: "all films", "new": "new releases", rep: "repertory", film: "on film" };
  var SORT_SUM = { "new": "newest first", pop: "trending first", az: "A to Z" };
  function renderSummary() { $("ssum").textContent = KIND_SUM[state.kind] + ", " + SORT_SUM[state.sort]; }

  // ---- Film cards ----------------------------------------------------------------

  function posterHTML(i, cls) {
    var f = films[i];
    if (!f.posters.length) return fallbackHTML(f);
    return '<img' + (cls ? ' class="' + cls + '"' : "") + ' src="' + esc(f.posters[0]) + '" data-f="' + i + '" data-n="0" alt="' +
      (cls ? "" : "Poster for " + esc(f.t)) + '" loading="lazy" decoding="async" referrerpolicy="no-referrer">';
  }
  function fallbackHTML(f) { return '<span class="fallback" aria-hidden="true">' + esc(f.t) + "</span>"; }

  // A broken poster tries the film's next image, then a typeset placeholder.
  document.addEventListener("error", function (e) {
    var img = e.target;
    if (!img || img.tagName !== "IMG" || img.dataset.f === undefined) return;
    var f = films[+img.dataset.f], n = +img.dataset.n + 1;
    if (n < f.posters.length) { img.dataset.n = n; img.src = f.posters[n]; return; }
    if (img.classList.contains("th")) { img.removeAttribute("src"); img.dataset.f = ""; return; }
    img.outerHTML = fallbackHTML(f);
  }, true);

  // The poster, like the title, opens the film's page. One link per card for keyboards and screen
  // readers: the title's; the poster's is skipped (tabindex -1, aria-hidden).
  function posterBlock(i, href) {
    var f = films[i], img = f.posters.length ? posterHTML(i, "art") : fallbackHTML(f);
    return '<a class="plink" href="' + href + '" data-film="' + i + '" tabindex="-1" aria-hidden="true">' + img + "</a>";
  }
  // "United Kingdom, 2026, 1h 58m, R, Metacritic 77" on the film page: country only when not the US;
  // Metacritic as the film's Wikipedia article reports it (nothing sorts by it).
  function factsOf(f) {
    var where = f.countries.filter(function (c) { return c !== "US"; }).slice(0, 1).map(function (c) { return COUNTRY ? COUNTRY.of(c) : c; });
    return where.concat([f.year, f.runtime ? runtime(f.runtime) : "", f.rating, f.mc != null ? "Metacritic " + f.mc : ""])
      .filter(Boolean).join(", ");
  }

  // A run of times in plain text, "11:50 am 1:45 pm 4:30 pm", each with its am/pm.
  function timesHTML(list, f, t, sh) {
    return list.map(function (s) {
      var own = ownTag(s, sh), tag = own ? "<sup>" + esc(shortTag(own)) + "</sup>" : "", label = "Times vary";
      if (s.hm) {
        var h = +s.hm.slice(0, 2), ap = h < 12 ? "am" : "pm";
        label = ((h % 12) || 12) + ":" + s.hm.slice(3) + ' <span class="ap">' + ap + "</span>";
      }
      return '<button type="button" class="time' + (isPast(s) ? " past" : "") + '" data-i="' + shows.indexOf(s) + '" aria-label="' +
        esc(f.t) + ", " + (s.hm ? longTime(s.hm) : "times vary") + ", " + esc(t.name || "") + '">' + label + tag + "</button>";
    }).join("");
  }

  // All dates and search extras: when a film plays at one theater, at a glance (Corey, Nov 2026: with
  // the film page for exact times, this line only needs where and when).
  //   one day              "Thu Nov 19, 4:15 pm 7:00 pm": the times are buttons for tickets (cardHTML)
  //   a run                "Nov 19 – 22" (up to two dark days in between still count as one run)
  //   to the posted end    "from Nov 12": theaters post their current films a week at a time (Nov 12,
  //                        2026: nearly every theater, the Sie too, through Wed Nov 18 or Thu Nov 19),
  //                        so a run that reaches that edge (POSTED, per chain) or the last date the
  //                        theater has posted at all (THEATER_END) hasn't ended; only one that stops
  //                        short has. The Dairy and CU post whole runs: "Queen at Sea Nov 12 – 14".
  //   separate runs/dates  "Nov 14 – 15, 21 – 22", "Nov 19, Dec 3, 10" (repertory, prints, weekend
  //                        events): up to three, then "and N more dates"
  var RUN_GAP = 3;   // days between two showings that still make one run (Fatherland at the Sie skips Mon–Tue)
  function weekdayDate(d) { return dateObj(d).toLocaleDateString("en-US", { weekday: "short" }) + " " + shortDate(d); }   // "Thu Nov 12"
  function whenHTML(list, th) {   // two or more dates (one day is drawn with its times in cardHTML)
    var dates = Array.from(new Set(list.map(function (s) { return s.d; }))).sort();
    var segs = [];   // runs of dates no more than RUN_GAP days apart
    dates.forEach(function (d, n) {
      if (n && dayDiff(dates[n - 1], d) <= RUN_GAP) segs[segs.length - 1][1] = d; else segs.push([d, d]);
    });
    var first = dates[0], last = dates[dates.length - 1];
    if (segs.length === 1) {
      var edge = POSTED[chainKey(th)];
      if ((edge && last >= edge && dayDiff(edge, last) <= 7) || (THEATER_END[th] && last >= THEATER_END[th])) return "from " + esc(shortDate(first));
    }
    var prevMonth = null, out = segs.slice(0, 3).map(function (g) {   // "Nov 14 – 15, 21 – 22": the month only when it changes
      var a = g[0].slice(0, 7) === prevMonth ? String(+g[0].slice(8)) : shortDate(g[0]);
      var z = g[1] === g[0] ? "" : " – " + (g[1].slice(0, 7) === g[0].slice(0, 7) ? String(+g[1].slice(8)) : shortDate(g[1]));
      prevMonth = g[1].slice(0, 7);
      return esc(a + z);
    }).join(", ");
    var rest = segs.slice(3).reduce(function (n, g) { return n + dates.filter(function (d) { return d >= g[0] && d <= g[1]; }).length; }, 0);
    return out + (rest ? " and " + rest + " more date" + (rest > 1 ? "s" : "") : "");
  }

  function sortFilms(ids) {
    var key = {
      // Newest: new releases by Denver release week (latest first, upcoming on top) and, within a
      // week, by Trending; then repertory by original release; special events last.
      new: function (f) {
        if (f.event) return null;   // events sort after every film
        // Weeks are 6.048e8 ms apart and the Trending bonus stays far below that, so it orders
        // films within a week without crossing weeks (lower trend score = more trending).
        if (!f.rep) return f.opened ? 1e13 + Date.parse(releaseWeek(f.opened)) + (f.trend != null ? 1e6 - f.trend : 0) : null;
        var r = f.rel || (f.year ? f.year + "-07-01" : null); return r ? Date.parse(r) : null;
      },
      // Trending: the scraper's 50/50 blend of TMDB popularity and 7-day Wikipedia views (by rank).
      pop: function (f) { return f.trend != null ? -f.trend : f.id && f.pop != null ? -1e6 + f.pop : null; }
    }[state.sort];
    return ids.sort(function (a, b) {
      var fa = films[a], fb = films[b], byTitle = fa.t.localeCompare(fb.t);
      if (!key) return byTitle;
      var ka = key(fa), kb = key(fb);
      if (ka == null || kb == null) return (ka == null) - (kb == null) || byTitle;   // no data: last
      return kb - ka || byTitle;
    });
  }

  function renderFilms() {
    var ds = dayShows(state.day), byFilm = new Map();
    ds.forEach(function (s) { if (!byFilm.has(s.f)) byFilm.set(s.f, []); byFilm.get(s.f).push(s); });
    var ids = sortFilms(Array.from(byFilm.keys()));

    var all = state.day === ALL;
    // Searching also finds a film beyond the chosen theaters/day ("Fjord" only at AMC Westminster):
    // those matches follow the normal results as compact two-week cards.
    var elsewhere = new Map();
    // Only search reaches past the chosen day and theaters. "On film" is a plain filter like the
    // other Show choices (Nov 2026: its own "On film on other dates" sections read as clutter);
    // All dates lists every print coming up, Now playing / Coming soon / Further out.
    if (state.q) {
      shows.forEach(function (s) {
        var inRange = s.d >= days[0];   // any date we have (some theaters list months out)
        if (byFilm.has(s.f) || !inRange || isPast(s) || (state.q && !hitOf(s.f))) return;
        if (!kindOk(s)) return;
        if (!elsewhere.has(s.f)) elsewhere.set(s.f, []); elsewhere.get(s.f).push(s);
      });
    }
    // Split the extra matches: your theaters on other dates, then other theaters (a film can be in both).
    var split = function (mine) {
      var m = new Map();
      elsewhere.forEach(function (list, i) {
        var part = list.filter(function (s) { return state.theaters.has(s.th) === mine; });
        if (part.length) m.set(i, part);
      });
      return m;
    };
    var otherDates = split(true), otherTheaters = split(false);
    var order = function (m) {
      var ids = sortFilms(Array.from(m.keys()));
      if (state.kind === "film") {   // prints: soonest screening first
        var soonest = function (i) { return m.get(i).reduce(function (x, s) { return (s.d + s.hm) < x ? s.d + s.hm : x; }, "9999"); };
        ids.sort(function (a, b) { return soonest(a).localeCompare(soonest(b)); });
      }
      return ids;
    };
    var extraIds = Array.from(elsewhere.keys());

    if (!ids.length && !extraIds.length) {
      // One message for every Show choice (On film included): "Nothing matches on this day. Try another
      // day or more theaters." Clearing the search is only suggested when there is one.
      var tries = (all ? [] : ["another day"]).concat("more theaters");
      $("grid").innerHTML = '<p class="empty">' + (state.theaters.size
        ? "Nothing matches" + (all ? "" : " on this day") + ". Try " + (state.q ? tries.join(", ") + ", or clear the search." : tries.join(" or ") + ".")
        : "Pick at least one theater above to see films.") + "</p>";
      return;
    }
    var cardHTML = function (i, other) {   // other: the Map of extra matches this card comes from
      var f = films[i], list = (other || byFilm).get(i).slice(), venues = new Map(), asSpan = all || !!other;
      list.sort(function (a, b) { return (a.d + (a.hm || "")).localeCompare(b.d + (b.hm || "")); })
        .forEach(function (s) { if (!venues.has(s.th)) venues.set(s.th, []); venues.get(s.th).push(s); });
      var since = f.opened ? dayDiff(f.opened, asSpan ? days[0] : state.day) : null;
      var fresh = f.rep || f.event || since == null ? "" : since < 0 ? "Opens " + shortDate(f.opened) : since <= 6 ? "Opening week" : "";
      var flag = f.event ? "Special event" : fresh;   // events (no TMDB match) say so; they sort and behave differently
      // "Indie" and "International" tags are on hold (Nov 2026): the Indie guess (TMDB lists
      // producers, not distributors) wasn't reliable, and Corey wants both or neither. The data
      // (film_meta.indie / .intl) is still in data.json.
      // Day view: theaters nearest first (same order as the checklist, so it follows the zip).
      var order = theaters.slice().sort(function (a, b) { return (miles(a) || 0) - (miles(b) || 0); }).map(function (t) { return t.key; });
      // Two weeks / search: theaters by their next showing, soonest first; otherwise in the usual order.
      var vlist = Array.from(venues.entries()).sort(asSpan ? function (a, b) { return (a[1][0].d + a[1][0].hm).localeCompare(b[1][0].d + b[1][0].hm); }
        : function (a, b) { return order.indexOf(a[0]) - order.indexOf(b[0]); });
      var vhtml = vlist.map(function (e, k) {
        var t = theaterOf(e[0]) || {};
        if (asSpan) {   // one line per theater: where and when ("Mayan Nov 19 – 22")
          var shs = shared(e[1]), lbl = sharedLabel(shs), extra = k >= SPAN_SHOWN ? " extra" : "";
          var name = esc((TINY[e[0]] || tName(e[0])) + (lbl ? ", " + lbl : ""));   // "Alamo, 35mm"
          // One day: its times, each opening its tickets like any other time on the site.
          if (e[1].every(function (s) { return s.d === e[1][0].d; }))
            return '<div class="venue line' + extra + '"><span class="vn">' + name + '</span><span class="when">' + esc(weekdayDate(e[1][0].d)) +
              (e[1][0].hm ? "," : "") + '</span><span class="times">' + timesHTML(e[1], f, t, shs) + "</span></div>";
          // Dates only ("Nov 19 – 22", "from Nov 12"): the line opens the film page on its first date.
          return '<a class="venue line' + extra + '" href="' + filmHref(i, e[1][0].d) + '" data-film="' + i + '">' +
            '<span class="vn">' + name + '</span><span class="when">' + whenHTML(e[1], e[0]) + "</span></a>";
        }
        // A format / language every showing here shares ("Regal Colorado, IMAX") goes with the theater, not on each time.
        var sh = shared(e[1]), lbl = sharedLabel(sh);
        var label = (TINY[e[0]] || tName(e[0])) + (lbl ? ", " + lbl : "");
        return '<div class="venue"><span class="vn">' + esc(label) + '</span><div class="times">' + timesHTML(e[1], f, t, sh) + "</div></div>";
      }).join("");
      // The film page picks up where the reader was: the day they're browsing, or All dates from All
      // dates. Search's extra matches (other dates / theaters) open on the film's usual first view.
      var href = filmHref(i, other ? null : all ? ALL : state.day);
      return '<article class="card"><div class="poster">' + posterBlock(i, href) + "</div>" +
        (flag ? '<p class="flag">' + esc(flag) + "</p>" : "") +
        // The title (and the poster) open the film's own page: every date and theater, as on a ticketing site.
        '<h3 class="title"><a href="' + href + '" data-film="' + i + '">' + esc(f.t) + "</a></h3>" +
        (langLine(f) ? '<p class="lang">' + esc(langLine(f)) + "</p>" : "") +
        // Found by someone in it or its genre, not its title: say so, or the match looks like a mistake.
        (state.q && hitOf(i) && hitOf(i).why ? '<p class="why">' + esc(hitOf(i).why) + "</p>" : "") +
        '<div class="venues">' + vhtml + "</div>" +
        (asSpan && vlist.length > SPAN_SHOWN ? '<button type="button" class="more all" aria-expanded="false" data-label="Show all ' + vlist.length + ' theaters">Show all ' + vlist.length + " theaters</button>" : "") +
        '<button type="button" class="more" hidden>Show all times</button></article>';
    };
    if (all) {   // now playing (by the chosen sort); coming soon in the two weeks; further out (some theaters only)
      var firstDay = function (i) { return byFilm.get(i).reduce(function (m, s) { return s.d < m ? s.d : m; }, "9999"); };
      var lastDay = days[days.length - 1];
      // Now playing: a showing today, or a new release already open in Denver that's only off for a
      // day or so (a dark day, a gap between theaters). Repertory and special events need today.
      var isNow = function (i) {
        var f = films[i], d = firstDay(i);
        return d === days[0] || (!f.rep && !f.event && !!f.opened && f.opened <= days[0] && dayDiff(days[0], d) <= RUN_GAP_DAYS);
      };
      var bySoonest = function (a, b) { return firstDay(a).localeCompare(firstDay(b)) || films[a].t.localeCompare(films[b].t); };
      var now = ids.filter(isNow);
      var soon = ids.filter(function (i) { return !isNow(i) && firstDay(i) <= lastDay; }).sort(bySoonest);
      var later = ids.filter(function (i) { return !isNow(i) && firstDay(i) > lastDay; }).sort(bySoonest);
      var grid = function (list) { return '<div class="grid">' + list.map(function (i) { return cardHTML(i); }).join("") + "</div>"; };
      $("grid").innerHTML = (now.length ? '<h3 class="group">Now playing</h3>' + grid(now) : "") +
        (soon.length ? '<h3 class="group">Coming soon</h3>' + grid(soon) : "") +
        // Only the Sie, Landmark and Alamo list this far ahead (the chains' feeds go two weeks out).
        (later.length ? '<h3 class="group">Further out</h3><p class="group-note">' + FURTHER_NOTE + "</p>" + grid(later) : "");
    } else if (state.kind === "all") {   // everything: new releases, then repertory, then one-offs, each in the chosen sort
      $("grid").innerHTML = [["New releases", function (f) { return !f.rep && !f.event; }], ["Repertory", function (f) { return f.rep && !f.event; }],
        ["Special events", function (f) { return f.event; }]].map(function (g) {
        var part = ids.filter(function (i) { return g[1](films[i]); });
        return part.length ? '<h3 class="group">' + g[0] + '</h3><div class="grid">' + part.map(function (i) { return cardHTML(i); }).join("") + "</div>" : "";
      }).join("") || '<p class="empty">Nothing matches at these theaters on this day.</p>';
    } else {
      $("grid").innerHTML = ids.length ? '<div class="grid">' + ids.map(function (i) { return cardHTML(i); }).join("") + "</div>"
        : '<p class="empty">Nothing matches at these theaters on this day.</p>';
    }
    [[otherDates, "Playing on other dates"], [otherTheaters, "Playing at other theaters"]].forEach(function (g) {
      if (!g[0].size) return;
      $("grid").innerHTML += '<h3 class="group">' + g[1] + '</h3><div class="grid">' +
        order(g[0]).map(function (i) { return cardHTML(i, g[0]); }).join("") + "</div>";
    });
    clampVenues();
  }

  // Several theaters can make a card's times run far past its poster: clamp the list and offer
  // "Show all times" where that hides a good few lines (measured in pixels, after layout).
  // Hiding just a line or two behind a button made the card *shrink* when expanded (the button
  // went away, a few px of times came in), so those cards just show everything.
  function clampVenues() {
    document.querySelectorAll("#grid .card").forEach(function (card) {
      var v = card.querySelector(".venues"), btn = card.querySelector(".more:not(.all)");
      if (!v || !btn || card.classList.contains("expanded")) return;
      v.classList.remove("clamp");
      var over = v.scrollHeight > CLAMP_PX + CLAMP_SLACK;
      v.classList.toggle("clamp", over);
      btn.hidden = !over;
      if (over) {
        var n = v.querySelectorAll(".venue").length;
        btn.textContent = btn.dataset.label = n > 1 ? "Show all " + n + " theaters" : "Show all times";
        btn.setAttribute("aria-expanded", "false");
      }
    });
  }
  // "Show all" / "Show fewer": collapsing keeps the button where it was on screen, so the page
  // doesn't jump out from under a reader who scrolled down through a long list.
  function toggleMore(b) {
    var card = b.closest(".card"), y = b.getBoundingClientRect().top, theaters = b.classList.contains("all");
    var open = !card.classList.contains(theaters ? "all-th" : "expanded");
    card.classList.toggle(theaters ? "all-th" : "expanded", open);
    if (!theaters) card.querySelector(".venues").classList.toggle("clamp", !open);
    b.textContent = open ? b.dataset.label.replace(/^Show all( \d+)?/, "Show fewer") : b.dataset.label;   // "Show fewer theaters"
    b.setAttribute("aria-expanded", open);
    if (!open) window.scrollBy(0, b.getBoundingClientRect().top - y);
  }

  // ---- Film page: every upcoming date and theater for one film ------------------------
  // Like a film's page on a ticketing site: the details, a strip of every date it plays (up to 90
  // days out where the theater lists that far), and for the chosen date every theater showing it,
  // nearest first, with its times. Its own address (#film/wild-horse-nine) so the newsletter can
  // link straight to it. It leaves the reader's theater picks, day and search alone.

  var FP_SHOWN = 6;   // theaters listed before "Show all N theaters"
  var FP_DATES = 5;   // All dates: a theater's dates listed before "Show all N dates"
  var FP_FEW = 4;     // a film on this many dates or fewer opens on All dates
  var THEATER_END = {};   // theater -> the last date it has posted (set in load)
  var POSTED = {};        // chain -> how far it has posted its current films: the usual last date (set in load)
  var POSTED_MIN = 3;     // current films that must stop on one date before it counts as the posting edge
  var WHOLE_RUNS = { dairy: true, cu: true };   // sources that list a film's whole run, so its last date is the end
  function chainKey(th) { return th.split("_")[0]; }   // "amc_westminster" -> "amc", "landmark_greenwood" -> "landmark"
  var filmKey = [], keyFilm = {}, BASE_TITLE = document.title;
  function filmHref(i, d) { return "#film/" + filmKey[i] + (d ? "/" + d : ""); }
  function upcoming(s) { return s.d > NOW.day || (s.d === NOW.day && !isPast(s)); }
  function filmDates(i) {
    return Array.from(new Set(shows.filter(function (s) { return s.f === i && upcoming(s); }).map(function (s) { return s.d; }))).sort();
  }
  function fpFlag(f) {
    if (f.event) return "Special event";
    if (f.rep || !f.opened) return "";
    var since = dayDiff(f.opened, NOW.day);
    return since < 0 ? "Opens " + shortDate(f.opened) : since <= 6 ? "Opening week" : "";
  }
  function renderFilmPage() {
    var i = state.film, page = $("filmpage");
    var back = '<p class="fp-nav"><button type="button" id="fpBack">← All films</button></p>';
    if (i == null) {
      page.innerHTML = back + '<p class="empty">That film isn’t playing at any theater we list right now.</p>';
      return;
    }
    var f = films[i], dates = filmDates(i), facts = factsOf(f), flag = fpFlag(f);
    // A film on only a few dates opens on All dates (everything at once); otherwise on its first date.
    // On a single date there's no All dates: it would only repeat that day (Corey, Nov 2026).
    var oneDate = dates.length === 1;
    if (oneDate ? state.fpDay !== dates[0] : state.fpDay !== ALL && dates.indexOf(state.fpDay) < 0) {
      state.fpDay = oneDate ? dates[0] : dates.length && dates.length <= FP_FEW ? ALL : dates[0] || null; state.fpAll = false; state.fpOpen = {};
    }
    var allDates = state.fpDay === ALL;
    var html = back + '<div class="fp-head"><div class="fp-poster">' + (f.posters.length ? posterHTML(i, "fp-img") : fallbackHTML(f)) + "</div>" +
      '<div class="fp-main">' + (flag ? '<p class="flag">' + esc(flag) + "</p>" : "") +
      '<h2 id="fpTitle" tabindex="-1">' + esc(f.t) + "</h2>" + (langLine(f) ? '<p class="lang">' + esc(langLine(f)) + "</p>" : "") +
      (f.dirs.length ? '<p class="dir">' + esc(f.dirs.join(", ")) + "</p>" : "") +
      (facts ? '<p class="facts">' + esc(facts) + "</p>" : "") +
      // Phones show three lines of the synopsis (so the dates and times start on the first screen) and "More".
      (f.about ? '<p class="about" id="fpAbout">' + esc(f.about) + '</p><button type="button" class="fp-more-about" id="fpAboutMore" aria-controls="fpAbout" aria-expanded="false" hidden>More</button>' : "") +
      (f.id ? '<p class="links"><a href="https://letterboxd.com/tmdb/' + f.id + '/" target="_blank" rel="noopener">View on Letterboxd</a></p>' : "") +
      "</div></div>";
    if (!dates.length) {
      page.innerHTML = html + '<p class="empty">No more showtimes at the theaters we list.</p>';
      fpAboutFits();
      return;
    }
    html += '<nav class="days fp-days" aria-label="Dates for ' + esc(f.t) + '">' + (oneDate ? "" :
      '<button type="button" class="day" data-fd="' + ALL + '" aria-pressed="' + allDates + '">' +
      '<span class="dm">&nbsp;</span><span class="dn">All</span><span class="dw">dates</span></button>') + dates.map(function (d) {
      return '<button type="button" class="day" data-fd="' + d + '" aria-pressed="' + (d === state.fpDay) + '" aria-label="' + longDate(d) + '">' +
        dayFace(d) + "</button>";
    }).join("") + "</nav>";
    // Every theater showing it, nearest first (as in the checklist): on the chosen date its times; on
    // All dates a line per date ("Thu Nov 12  3:00 pm 6:15 pm"), the first FP_DATES, then "Show all".
    var by = new Map();
    shows.filter(function (s) { return s.f === i && (allDates ? s.d >= NOW.day : s.d === state.fpDay); })
      .sort(function (a, b) { return (a.d + (a.hm || "")).localeCompare(b.d + (b.hm || "")); })
      .forEach(function (s) { if (!by.has(s.th)) by.set(s.th, []); by.get(s.th).push(s); });
    var dist = function (k) { var m = miles(theaterOf(k) || {}); return m == null ? 1e9 : m; };
    var keys = Array.from(by.keys()).sort(function (a, b) { return dist(a) - dist(b); });
    var wd = function (d) { return dateObj(d).toLocaleDateString("en-US", { weekday: "short" }) + " " + shortDate(d); };
    html += '<h3 class="fp-date">' + esc(allDates ? "All dates" : longDate(state.fpDay)) + '<span> at ' + keys.length + " theater" + (keys.length > 1 ? "s" : "") + "</span></h3>" +
      '<div class="fp-venues' + (allDates ? " span" : "") + (state.fpAll ? " all-th" : "") + '">' + keys.map(function (k, n) {
        var t = theaterOf(k) || { name: k }, list = by.get(k), sh = shared(list), lbl = sharedLabel(sh), mi = miles(t);
        var head = '<p class="vn"><span>' + esc(tName(k)) + (lbl ? '<span class="lbl">, ' + esc(lbl) + "</span>" : "") + "</span>" +
          (mi != null ? '<span class="mi">' + mi.toFixed(1) + " mi</span>" : "") + "</p>";
        if (!allDates) return '<div class="venue' + (n >= FP_SHOWN ? " extra" : "") + '">' + head + '<div class="times">' + timesHTML(list, f, t, sh) + "</div></div>";
        var byDay = new Map();
        list.forEach(function (s) { if (!byDay.has(s.d)) byDay.set(s.d, []); byDay.get(s.d).push(s); });
        var open = !!state.fpOpen[k], lines = Array.from(byDay.entries()).map(function (e, j) {
          return '<div class="fp-day' + (j >= FP_DATES ? " extra-d" : "") + '"><span class="fd">' + esc(wd(e[0])) + '</span><div class="times">' +
            timesHTML(e[1], f, t, sh) + "</div></div>";
        }).join("");
        return '<div class="venue' + (n >= FP_SHOWN ? " extra" : "") + (open ? " all-d" : "") + '">' + head + lines +
          (byDay.size > FP_DATES ? '<button type="button" class="more" data-fth="' + k + '" aria-expanded="' + open + '">' +
            (open ? "Show fewer dates" : "Show all " + byDay.size + " dates") + "</button>" : "") + "</div>";
      }).join("") + "</div>" +
      (keys.length > FP_SHOWN ? '<button type="button" class="more" id="fpMore" aria-expanded="' + state.fpAll + '">' +
        (state.fpAll ? "Show fewer theaters" : "Show all " + keys.length + " theaters") + "</button>" : "");
    page.innerHTML = html;
    fpAboutFits();
    var sel = page.querySelector('.fp-days [aria-pressed="true"]'); if (sel) sel.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
  function fpAboutFits() {   // "More" only when the three lines hide something
    var a = $("fpAbout"), m = $("fpAboutMore");
    if (a && m) m.hidden = !a.classList.contains("open") && a.scrollHeight <= a.clientHeight + 1;
  }
  function openFilm(i, day) {   // day: open on that date (a theater line in All dates links its first one)
    var was = state.film;
    state.film = i; if (was !== i) { state.fpDay = null; state.fpAll = false; state.fpOpen = {}; }
    if (day) { state.fpDay = day; state.fpAll = false; state.fpOpen = {}; }
    document.body.classList.add("fp-open"); $("filmpage").hidden = false;
    renderFilmPage();
    document.title = (i == null ? "Not playing" : films[i].t + " showtimes") + " · " + BASE_TITLE;
    window.scrollTo(0, 0);
    var h = $("fpTitle"); if (h) h.focus({ preventScroll: true });
  }
  function closeFilm() {
    var i = state.film;
    if (!document.body.classList.contains("fp-open")) return;
    state.film = null;
    document.body.classList.remove("fp-open"); $("filmpage").hidden = true; $("filmpage").innerHTML = "";
    document.title = BASE_TITLE;
    clampVenues(); edges();
    window.scrollTo(0, state.fpScroll);
    var a = i != null && document.querySelector('#grid .title a[data-film="' + i + '"]'); if (a) a.focus({ preventScroll: true });
  }
  // "#film/<key>" opens a film's page; anything else shows the listings.
  function route() {
    var m = /^#film\/([^/]+)(?:\/(\d{4}-\d{2}-\d{2}|all))?$/.exec(location.hash);
    if (!m) return closeFilm();
    var k = decodeURIComponent(m[1]);
    openFilm(keyFilm[k] != null ? keyFilm[k] : null, m[2]);
  }
  function leaveFilm() {   // back to the listings: the browser's back when we came from them
    if (state.fpFromList) { state.fpFromList = false; history.back(); return; }
    history.replaceState(null, "", location.pathname + location.search);
    closeFilm();
  }

  // ---- Schedule --------------------------------------------------------------------

  function renderSchedule() {
    var ds = dayShows(state.day).filter(function (s) { return s.hm; })
      .sort(function (a, b) { return a.hm.localeCompare(b.hm) || films[a.f].t.localeCompare(films[b.f].t); });
    var past = ds.filter(isPast), shown = state.showEarlier ? ds : ds.filter(function (s) { return !isPast(s); });
    if (!ds.length) { $("sched").innerHTML = '<p class="empty">No showtimes match.</p>'; schedEdges(); return; }
    var hours = new Map();
    shown.forEach(function (s) { var h = s.hm.slice(0, 2); if (!hours.has(h)) hours.set(h, []); hours.get(h).push(s); });
    var html = shown.length ? "" : '<p class="empty">Everything has started for today.</p>';
    hours.forEach(function (rows, h) {
      var n = +h, half = n < 12 ? "am" : "pm";
      html += '<div class="hour"><p class="h">' + ((n % 12) || 12) + "<small>" + half + "</small>" + '</p><div class="rows">' +
        rows.map(function (s) {
          var f = films[s.f], extra = tagOf(s);
          return '<button type="button" class="row' + (isPast(s) ? " past" : "") + '" data-i="' + shows.indexOf(s) + '"><b>' + hm12(s.hm).replace(" ", "\u2009") +
            '</b> <span class="ft">' + esc(f.t) + '</span> <span class="th">' + esc(TINY[s.th] || tName(s.th)) + (extra ? ", " + esc(extra) : "") + "</span></button>";
        }).join("") + "</div></div>";
    });
    if (past.length) html += '<button type="button" class="earlier" id="earlier">' + (state.showEarlier ? "Hide " : "Show ") + past.length + " earlier today</button>";
    $("sched").innerHTML = html;
    schedEdges();
  }
  // Desktop: the schedule column scrolls on its own, with no scrollbar (like the theater row): the
  // side with more fades out instead. Wheel / trackpad / keyboard scroll it as usual.
  function schedEdges() {
    var col = $("sched").parentNode, max = col.scrollHeight - col.clientHeight;
    var scrolls = max > 2 && getComputedStyle(col).overflowY !== "visible";
    col.classList.toggle("more-t", scrolls && col.scrollTop > 2);
    col.classList.toggle("more-b", scrolls && max - col.scrollTop > 2);
  }

  // ---- Showtime sheet + add to calendar -----------------------------------------------

  function pad(n) { return String(n).padStart(2, "0"); }
  function stamp(d, hm) { return d.replace(/-/g, "") + "T" + hm.replace(":", "") + "00"; }
  function endOf(s) {
    if (s.end) return { d: s.end.slice(0, 10), hm: s.end.slice(11, 16) };
    var o = new Date(s.d + "T" + s.hm + ":00"); o.setMinutes(o.getMinutes() + (films[s.f].runtime || 120));   // 2 h when unknown (calendar only)
    return { d: o.getFullYear() + "-" + pad(o.getMonth() + 1) + "-" + pad(o.getDate()), hm: pad(o.getHours()) + ":" + pad(o.getMinutes()) };
  }
  function slug(t) { return t.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "showtime"; }
  function icsEsc(t) { return String(t).replace(/([,;\\])/g, "\\$1").replace(/\n/g, "\\n"); }

  function calendarLinks(s) {
    var f = films[s.f], t = theaterOf(s.th) || { name: s.th }, e = endOf(s);
    var title = f.t + " at " + t.name, details = (s.url ? "Tickets: " + s.url + "\n" : "") + "From Denver Showtimes";
    var google = "https://calendar.google.com/calendar/render?action=TEMPLATE&text=" + encodeURIComponent(title) +
      "&dates=" + stamp(s.d, s.hm) + "/" + stamp(e.d, e.hm) + "&ctz=America/Denver&location=" + encodeURIComponent(t.name) +
      "&details=" + encodeURIComponent(details);
    var outlook = "https://outlook.live.com/calendar/0/deeplink/compose?path=/calendar/action/compose&rru=addevent&subject=" +
      encodeURIComponent(title) + "&startdt=" + s.d + "T" + s.hm + ":00&enddt=" + e.d + "T" + e.hm + ":00&location=" +
      encodeURIComponent(t.name) + "&body=" + encodeURIComponent(details);
    var ics = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//denver-showtimes//EN", "CALSCALE:GREGORIAN",
      "BEGIN:VTIMEZONE", "TZID:America/Denver",
      "BEGIN:DAYLIGHT", "TZOFFSETFROM:-0700", "TZOFFSETTO:-0600", "TZNAME:MDT", "DTSTART:19700308T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT",
      "BEGIN:STANDARD", "TZOFFSETFROM:-0600", "TZOFFSETTO:-0700", "TZNAME:MST", "DTSTART:19701101T020000", "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD",
      "END:VTIMEZONE", "BEGIN:VEVENT", "UID:" + s.id + "@denver-showtimes",
      "DTSTAMP:" + new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z",
      "DTSTART;TZID=America/Denver:" + stamp(s.d, s.hm), "DTEND;TZID=America/Denver:" + stamp(e.d, e.hm),
      "SUMMARY:" + icsEsc(title), "LOCATION:" + icsEsc(t.name), "DESCRIPTION:" + icsEsc(details),
      "END:VEVENT", "END:VCALENDAR"].join("\r\n");
    return { google: google, outlook: outlook, ics: URL.createObjectURL(new Blob([ics], { type: "text/calendar;charset=utf-8" })), end: e };
  }

  // Fandango's links go straight to the seats; the theater's own site skips Fandango's fee and earns
  // the chain's rewards, but needs the time picked again (Fandango's data has no chain showtime ids).
  var CHAINS = [["amctheatres.com", "AMC"], ["regmovies.com", "Regal"], ["harkins.com", "Harkins"], ["cinemark.com", "Cinemark"],
    ["emagine-entertainment.com", "Emagine"], ["marcustheatres.com", "Movie Tavern"]];
  function chainOf(url) {
    var host = ""; try { host = new URL(url).hostname; } catch (e) { return "the theater"; }
    for (var n = 0; n < CHAINS.length; n++) if (host === CHAINS[n][0] || host.slice(-CHAINS[n][0].length - 1) === "." + CHAINS[n][0]) return CHAINS[n][1];
    return "the theater";
  }
  function isFandango(url) { try { return /(^|\.)fandango\.com$/.test(new URL(url).hostname); } catch (e) { return false; } }

  var lastFocus = null, icsUrl = null;
  function openSheet(i) {
    var s = shows[i], f = films[s.f], t = theaterOf(s.th) || { name: s.th };
    var where = [t.name, s.scr, tagOf(s)].filter(Boolean).join(", "), links = s.hm ? calendarLinks(s) : null;
    icsUrl = links && links.ics;
    // No runtime from the theater or TMDB: the calendar entry still assumes 2 hours (it needs an
    // end), but the sheet shows only the start rather than a guessed end time.
    var guessed = !s.end && !f.runtime;
    var when = dateObj(s.d).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }) +
      (s.hm ? ", " + timeHTML(s.hm) + (guessed ? "" : " to " + timeHTML(links.end.hm)) : ", times vary");
    $("backdrop").innerHTML = '<div class="sheet" role="dialog" aria-modal="true" aria-labelledby="sheetT">' +
      (f.posters.length ? posterHTML(s.f, "sheet-poster") : '<div class="ph"></div>') +
      '<div><h3 id="sheetT">' + esc(f.t) + '</h3><div class="when">' + when + "</div>" +
      '<div class="where">' + esc(where) + "</div></div>" +
      '<div class="actions">' + (s.url ? '<a class="btn primary" href="' + esc(s.url) + '" target="_blank" rel="noopener">Get tickets' + (isFandango(s.url) ? " on Fandango" : "") + "</a>" : "") +
      (s.url && isFandango(s.url) && t.site ? '<a class="alt" href="' + esc(t.site) + '" target="_blank" rel="noopener">Or buy from ' + esc(chainOf(t.site)) + " directly</a>" : "") +
      // One "Add to calendar" button; its three choices open under it, so tickets stay the big button.
      (links ? '<button type="button" class="btn" id="calToggle" aria-expanded="false" aria-controls="calOpts">Add to calendar</button>' +
        '<div class="btn-row" id="calOpts" hidden><a class="btn" href="' + esc(links.google) + '" target="_blank" rel="noopener">Google</a>' +
        '<a class="btn" href="' + esc(links.outlook) + '" target="_blank" rel="noopener">Outlook</a>' +
        '<a class="btn" href="' + links.ics + '" download="' + slug(f.t) + '.ics">Apple / .ics</a></div>' : "") +
      '<button type="button" class="btn" id="closeSheet">Close</button></div></div>';
    lastFocus = document.activeElement;
    $("backdrop").hidden = false;
    var first = $("backdrop").querySelector("a, button"); if (first) first.focus();
  }
  function closeSheet() {
    $("backdrop").hidden = true; $("backdrop").innerHTML = "";
    if (icsUrl) { URL.revokeObjectURL(icsUrl); icsUrl = null; }
    if (lastFocus) lastFocus.focus();
  }

  // ---- Wiring ------------------------------------------------------------------------

  function setMode() {   // the two-week view has no schedule
    var all = state.day === ALL;
    $("layout").dataset.mode = all ? "span" : "day";
    var seg = document.querySelector(".seg"); if (seg) seg.hidden = all;
    if (all) {
      $("layout").dataset.view = "films";
      document.querySelectorAll("[data-v]").forEach(function (x) { x.setAttribute("aria-pressed", x.dataset.v === "films"); });
    }
  }
  function renderAll() { renderTheaters(); renderFilms(); if (state.day !== ALL) renderSchedule(); }
  // A new day from far down the page: come back up to the top of the films (under the sticky days).
  function toFilms() {
    var top = $("layout").getBoundingClientRect().top + window.scrollY - $("days").offsetHeight - 12;
    if (window.scrollY > top) window.scrollTo({ top: top });
  }
  function measure() { document.documentElement.style.setProperty("--days-h", $("days").offsetHeight + "px"); }

  function wire() {
    document.addEventListener("click", function (e) {
      if (e.target.id === "backdrop") return closeSheet();
      var fl = e.target.closest("a[data-film]");
      if (fl) {   // a film's page: remember where the reader was so "back" returns there
        if (!document.body.classList.contains("fp-open")) { state.fpScroll = window.scrollY; state.fpFromList = true; }
        return;   // the link itself changes the address; route() opens the page
      }
      var b = e.target.closest("button"); if (!b) return;
      if (b.id === "tToggle") {
        var open = !$("controls").classList.contains("open");
        $("controls").classList.toggle("open", open); b.setAttribute("aria-expanded", open); b.textContent = open ? "Done" : "Change";
        if (open) { state.tAll = false; pickShownTheaters(); renderTheaters(); }
        measure(); return;
      }
      if (b.id === "tMore") {   // collapsing keeps the button where it was on screen
        var y = b.getBoundingClientRect().top; state.tAll = !state.tAll;
        if (!state.tAll) pickShownTheaters();   // keeps any just checked further down the list
        renderTheaters();
        if (!state.tAll) window.scrollBy(0, b.getBoundingClientRect().top - y);
        return;
      }
      if (b.id === "closeSheet") return closeSheet();
      if (b.id === "fpBack") return leaveFilm();
      if (b.id === "fpAboutMore") {
        var ab = $("fpAbout"), more = !ab.classList.contains("open");
        ab.classList.toggle("open", more); b.textContent = more ? "Less" : "More"; b.setAttribute("aria-expanded", more); return;
      }
      if (b.dataset.fd) { state.fpDay = b.dataset.fd; state.fpAll = false; state.fpOpen = {}; renderFilmPage(); return; }
      if (b.dataset.fth) {   // All dates: one theater's every date; collapsing keeps the button where it was
        var ty = b.getBoundingClientRect().top, th = b.dataset.fth; state.fpOpen[th] = !state.fpOpen[th]; renderFilmPage();
        if (!state.fpOpen[th]) { var nb = document.querySelector('[data-fth="' + th + '"]'); if (nb) window.scrollBy(0, nb.getBoundingClientRect().top - ty); }
        return;
      }
      if (b.id === "fpMore") {   // collapsing keeps the button where it was on screen
        var fy = b.getBoundingClientRect().top; state.fpAll = !state.fpAll; renderFilmPage();
        if (!state.fpAll) window.scrollBy(0, $("fpMore").getBoundingClientRect().top - fy);
        return;
      }
      if (b.id === "calToggle") {
        var opts = $("calOpts"), show = opts.hidden; opts.hidden = !show; b.setAttribute("aria-expanded", show);
        if (show) opts.querySelector("a").focus(); return;
      }
      if (b.dataset.d) { state.day = b.dataset.d; state.showEarlier = false; setMode(); renderDays(); renderAll(); toFilms(); return; }
      if (b.dataset.k) {
        var k = b.dataset.k; state.theaters.has(k) ? state.theaters.delete(k) : state.theaters.add(k); state.radius = null;
        saveTheaters(); renderAll(); return;
      }
      if (b.dataset.r) {
        state.radius = b.dataset.r; applyRadius(); pickShownTheaters(); saveTheaters(); renderAll(); return;
      }
      // "clear" unchecks every theater so a reader can pick one or two without unchecking the rest.
      // An empty pick isn't kept: a reload starts from the default theaters again.
      if (b.id === "tClear") {
        state.theaters = new Set(); state.radius = null; pickShownTheaters(); saveTheaters(); renderAll(); return;
      }
      if (b.dataset.kind) {
        state.kind = b.dataset.kind;
        document.querySelectorAll("[data-kind]").forEach(function (x) { x.setAttribute("aria-pressed", x === b); });
        renderAll(); return;
      }
      if (b.dataset.s) {
        state.sort = b.dataset.s;
        document.querySelectorAll("[data-s]").forEach(function (x) { x.setAttribute("aria-pressed", x === b); });
        renderSummary(); renderFilms(); return;
      }
      if (b.dataset.v) {
        $("layout").dataset.view = b.dataset.v;
        document.querySelectorAll("[data-v]").forEach(function (x) { x.setAttribute("aria-pressed", x === b); });
        return;
      }
      if (b.classList.contains("more")) return toggleMore(b);
      if (b.id === "earlier") { state.showEarlier = !state.showEarlier; renderSchedule(); return; }
      if (b.dataset.i) openSheet(+b.dataset.i);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (!$("backdrop").hidden) return closeSheet();
      if (document.body.classList.contains("fp-open")) return leaveFilm();
    });
    var q = $("q"), clear = $("qClear");
    var setQ = function () { state.q = q.value.trim(); clear.hidden = !q.value; renderAll(); };
    q.addEventListener("input", setQ);
    q.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); q.blur(); } });   // closes the phone keyboard
    clear.addEventListener("click", function () { q.value = ""; setQ(); q.focus(); });
    $("zip").addEventListener("input", function (e) {
      var z = e.target.value.replace(/\D/g, "").slice(0, 5);
      if (z !== e.target.value) e.target.value = z;
      var ok = z.length === 5 && ZIPS[z];
      $("zipNote").hidden = !(z.length === 5 && !ok);
      if (ok) { state.zip = z; applyRadius(); pickShownTheaters(); renderAll(); }
    });
    window.addEventListener("resize", function () { measure(); clampVenues(); edges(); schedEdges(); fpAboutFits(); });
    if (document.fonts) document.fonts.ready.then(function () { clampVenues(); edges(); schedEdges(); });   // re-measure in Archivo
    // A tab left open overnight would keep yesterday as "today": reload when the Denver date changes.
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState !== "visible") return;
      var d = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Denver" }).format(new Date());
      if (d !== NOW.day) location.reload();
    });
    window.addEventListener("hashchange", route);
    $("tlist").addEventListener("scroll", edges, { passive: true });
    $("sched").parentNode.addEventListener("scroll", schedEdges, { passive: true });
    $("tPrev").addEventListener("click", function () { $("tlist").scrollBy({ left: -$("tlist").clientWidth * .8 }); });
    $("tNext").addEventListener("click", function () { $("tlist").scrollBy({ left: $("tlist").clientWidth * .8 }); });
  }

  var zipTable = fetch("zips.json").then(function (r) { return r.ok ? r.json() : {}; }).catch(function () { return {}; });
  fetch("data.json?_=" + Date.now(), { cache: "no-store" })
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (data) { return zipTable.then(function (z) { ZIPS = z; return data; }); })
    .then(function (data) {
      load(data); wire(); setMode(); renderSources(); renderDays(); renderAll(); measure();
      var sel = $("days").querySelector('[aria-pressed="true"]'); if (sel) sel.scrollIntoView({ block: "nearest", inline: "center" });
      if (location.hash) route();   // a link straight to a film's page
    })
    .catch(function (e) {
      $("grid").innerHTML = '<p class="empty">Couldn’t load showtimes (' + esc(e.message) + "). Try reloading the page.</p>";
    });
})();
