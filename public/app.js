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
    amc_arapahoe: "AMC Arapahoe Crossing" };
  var THEATER_SITES = [   // one link per company; each site lists its own locations
    ["Sie FilmCenter", "https://www.denverfilm.org/"],
    ["Landmark", "https://www.landmarktheatres.com/"],
    ["AMC", "https://www.amctheatres.com/"],
    ["Regal", "https://www.regmovies.com/"],
    ["Harkins", "https://www.harkins.com/"],
    ["Cinemark", "https://www.cinemark.com/"],
    ["Alamo Drafthouse", "https://drafthouse.com/denver"],
    ["Movie Tavern", "https://www.marcustheatres.com/"]   // Marcus runs it; movietavern.com's certificate had lapsed (Nov 2026)
  ];
  // Shortest names, for the times under a poster, the hour list and the "At Sie and Mayan" line.
  var TINY = { sie: "Sie", landmark: "Mayan", amc: "AMC 9+CO 10", regal_pavilions: "Regal Pavilions",
    alamo_sloans: "Alamo Sloans Lake", alamo_westminster: "Alamo Westminster", alamo_littleton: "Alamo Littleton",
    regal_colorado: "Regal Colorado", amc_westminster: "AMC Westminster",
    landmark_greenwood: "Landmark Greenwood Village", harkins_arvada: "Harkins Arvada", harkins_northfield: "Harkins Northfield",
    amc_cherry_creek: "AMC Cherry Creek", cinemark_belmar: "Cinemark Bel Mar", regal_river_point: "Regal River Point",
    cinemark_aurora: "Cinemark Aurora", regal_southglenn: "Regal SouthGlenn", regal_colorado_mills: "Regal Colorado Mills",
    amc_bowles: "AMC Bowles Crossing", amc_highlands_ranch: "AMC Highlands Ranch", movie_tavern_aurora: "Movie Tavern Aurora",
    amc_arapahoe: "AMC Arapahoe Crossing" };
  // Formats and languages (scraper's formats.py): IMAX, Dolby, film prints and 3D by name; every other
  // premium screen is "PLF"; "Subtitled" / "Dubbed". A theater whose showings all share one goes on its
  // line; mixed ones get a short red mark per time (anything not listed uses its own name).
  var FMT_TAG = { "IMAX": "IMAX", "IMAX 3D": "IMAX 3D", "IMAX 70mm": "IMAX 70", "Dolby": "Dolby", "Dolby 3D": "Dolby 3D",
    "3D": "3D", "16mm": "16mm", "35mm": "35mm", "70mm": "70mm", "VistaVision": "VV", "PLF": "PLF", "Premium Format": "PLF",
    "Subtitled": "Sub", "Dubbed": "Dub" };
  function fmtName(f) { return f === "Premium Format" ? "PLF" : f; }   // older data said "Premium Format"
  function tagOf(s) { return [s.fmt ? fmtName(s.fmt) : "", s.lang || ""].filter(Boolean).join(", "); }   // "IMAX, Subtitled"
  function shortTag(t) { return t.split(", ").map(function (x) { return FMT_TAG[x] || x; }).join(" "); }
  // Format and language are judged separately for a theater's showings: whatever all of them share
  // goes on the theater line ("Regal Pavilions, Subtitled"); only what differs is marked on a time
  // ("2:00 pm PLF"). Judged together, one PLF showing used to push "Sub" onto every time.
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
  function resolveLang(raw, f) {
    var m = /^(\w+) language$/.exec(raw || "");
    if (!m) return raw || null;
    var orig = f.olang === "cn" ? "Cantonese" : f.olang && LANGUAGE ? LANGUAGE.of(f.olang) : null;
    var same = orig === m[1] || (orig === "Chinese" && /^(Mandarin|Cantonese)$/.test(m[1]));
    // Only an English film in another language is surely a dub; any other mismatch just says the language.
    return same ? "Subtitled" : f.olang === "en" ? m[1] + " dub" : "In " + m[1];
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
  var state = { day: null, q: "", sort: "new", kind: "all", showEarlier: false, theaters: null, zip: DEFAULT_ZIP, radius: null, open: null,
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
        cast: m.cast || [], genres: m.genres || [], qt: fold(t),
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
  var TK_SHOWN = 5;         // phones: theaters in the opened checklist before "Show all 22 theaters"
  var CLAMP_PX = 210;       // a card's times stop here (styles.css .venues.clamp) ...
  var CLAMP_SLACK = 90;     // ... but only when that hides this much more: never a button for a line or two
  var WINDOW_DAYS = 14;     // the day strip: today + 14 (Sie, Landmark and Alamo list up to ~90 days out)
  var FURTHER_NOTE = "Sie, Landmark and Alamo only.";
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

  function renderDays() {
    $("days").innerHTML = '<button type="button" class="day" data-d="' + ALL + '" aria-pressed="' + (state.day === ALL) + '">' +
      '<span class="dm">&nbsp;</span><span class="dn">All</span><span class="dw">dates</span></button>' + days.map(function (d, n) {
      var rel = relDay(d), o = dateObj(d), wd = o.toLocaleDateString("en-US", { weekday: "short" });
      // Like a tear-off calendar: "Nov" over a big "10" over "Tue". Always the weekday, never "Today",
      // so every day keeps the same width; the month on every day reads right across Nov into Dec.
      return '<button type="button" class="day" data-d="' + d + '" aria-pressed="' + (d === state.day) + '" aria-label="' + (rel ? rel + ", " : "") + longDate(d) + '">' +
        '<span class="dm">' + o.toLocaleDateString("en-US", { month: "short" }) + '</span><span class="dn">' + o.getDate() + '</span><span class="dw">' + wd + "</span></button>";
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

  // Phones list the theaters top to bottom: the nearest few and any that are checked, the rest
  // behind "Show all 22 theaters" so Show / Sort aren't a long scroll away. Picked when the list
  // opens or the zip / distance changes, not on each tap, so a row never vanishes as it's unchecked.
  function pickShownTheaters() {
    var near = theaters.slice().sort(function (a, b) { return (miles(a) || 0) - (miles(b) || 0); });
    state.tShown = new Set(near.filter(function (t, n) { return n < TK_SHOWN || state.theaters.has(t.key); }).map(function (t) { return t.key; }));
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
    var more = $("tMore"); more.hidden = !hidden;
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

  // The poster is a button: tapping it lays the director, facts and synopsis over the art.
  // Special events (no TMDB match) have none of that, so their poster is just a picture.
  function posterBlock(i) {
    var f = films[i], img = f.posters.length ? posterHTML(i) : fallbackHTML(f);
    if (f.event) return '<span class="still">' + img + "</span>";
    var where = f.countries.filter(function (c) { return c !== "US"; }).slice(0, 1).map(function (c) { return COUNTRY ? COUNTRY.of(c) : c; });
    var facts = where.concat([f.year, f.runtime ? runtime(f.runtime) : "", f.rating]).filter(Boolean).join(", ");
    var open = state.open === i;
    return '<button type="button" data-p="' + i + '" aria-expanded="' + open + '" aria-label="' + esc(f.t) + (open ? ", hide details" : ", show details") + '">' + img + "</button>" +
      (open ? '<div class="info" data-p="' + i + '">' + (f.dirs.length ? '<p class="dir">' + esc(f.dirs.join(", ")) + "</p>" : "") +
        (facts ? '<p class="facts">' + esc(facts) + "</p>" : "") + (f.about ? "<p>" + esc(f.about) + "</p>" : "") +
        (f.id ? '<a href="https://letterboxd.com/tmdb/' + f.id + '/" target="_blank" rel="noopener">View on Letterboxd</a>' : "") + "</div>" : "");
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
    // "On film" too: prints are rare, so show the ones at other theaters and days as well.
    if (state.q || state.kind === "film") {
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
      $("grid").innerHTML = '<p class="empty">' + (state.kind === "film" && !state.q
        ? "Nothing is showing on film in the dates we have."
        : state.theaters.size ? "Nothing matches" + (all ? "" : " on this day") + ". Try " + (all ? "" : "another day, ") + "more theaters, or clear the search."
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
        if (asSpan) {   // one line per theater, "Alamo  Sat Nov 7, 5:00 pm  through Nov 11"; the first 3, then "Show all"
          var first = e[1][0], last = e[1][e[1].length - 1], o = dateObj(first.d), shs = shared(e[1]), lbl = sharedLabel(shs), own = ownTag(first, shs);
          var name = esc((TINY[e[0]] || tName(e[0])) + (lbl ? ", " + lbl : ""));   // "Alamo, 35mm"
          var day = o.toLocaleDateString("en-US", { weekday: "short" }) + " " + shortDate(first.d);
          return '<div class="venue line' + (k >= SPAN_SHOWN ? " extra" : "") + '"><span class="vn">' + name + '</span><button type="button" class="time next" data-i="' +
            shows.indexOf(first) + '" aria-label="' + esc(f.t) + ", next showing " + longDate(first.d) + " " + (first.hm ? longTime(first.hm) : "") + ", " + esc(t.name || "") + '">' +
            day + (first.hm ? ', <span class="nw">' + timeHTML(first.hm) + "</span>" : "") + (own ? "<sup>" + esc(shortTag(own)) + "</sup>" : "") + "</button>" +
            // How long it runs here, quietly after the next showing: "through Nov 11".
            (last.d !== first.d ? '<span class="thru">through ' + shortDate(last.d) + "</span>" : "") + "</div>";
        }
        // A format / language every showing here shares ("Regal Colorado, IMAX") goes with the theater, not on each time.
        var sh = shared(e[1]), lbl = sharedLabel(sh);
        var label = (TINY[e[0]] || tName(e[0])) + (lbl ? ", " + lbl : "");
        return '<div class="venue"><span class="vn">' + esc(label) + '</span><div class="times">' + timesHTML(e[1], f, t, sh) + "</div></div>";
      }).join("");
      return '<article class="card"><div class="poster">' + posterBlock(i) + "</div>" +
        (flag ? '<p class="flag">' + esc(flag) + "</p>" : "") +
        // The title opens the details too: people tap titles, and it's the hint the poster needs.
        '<h3 class="title">' + (f.event ? esc(f.t) : '<button type="button" data-p="' + i + '" aria-expanded="' + (state.open === i) + '">' + esc(f.t) + "</button>") + "</h3>" +
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
      }).join("") || '<p class="empty">No match at these theaters on this day.</p>';
    } else {
      $("grid").innerHTML = ids.length ? '<div class="grid">' + ids.map(function (i) { return cardHTML(i); }).join("") + "</div>"
        : '<p class="empty">' + (state.kind === "film" ? "Nothing on film" : "No match") + ' at these theaters' + (all ? "" : " on this day") + ".</p>";
    }
    var lead = state.kind === "film" && !state.q ? "On film" : "Playing";
    [[otherDates, lead + " on other dates"], [otherTheaters, lead + " at other theaters"]].forEach(function (g) {
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
    var o = new Date(s.d + "T" + s.hm + ":00"); o.setMinutes(o.getMinutes() + (films[s.f].runtime || 120));
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

  var lastFocus = null, icsUrl = null;
  function openSheet(i) {
    var s = shows[i], f = films[s.f], t = theaterOf(s.th) || { name: s.th };
    var where = [t.name, s.scr, tagOf(s)].filter(Boolean).join(", "), links = s.hm ? calendarLinks(s) : null;
    icsUrl = links && links.ics;
    var when = dateObj(s.d).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }) +
      (s.hm ? ", " + timeHTML(s.hm) + " to " + timeHTML(links.end.hm) : ", times vary");
    $("backdrop").innerHTML = '<div class="sheet" role="dialog" aria-modal="true" aria-labelledby="sheetT">' +
      (f.posters.length ? posterHTML(s.f, "sheet-poster") : '<div class="ph"></div>') +
      '<div><h3 id="sheetT">' + esc(f.t) + '</h3><div class="when">' + when + "</div>" +
      '<div class="where">' + esc(where) + (s.hm && !s.end && !f.runtime ? ", runtime unknown, 2h assumed" : "") + "</div></div>" +
      '<div class="actions">' + (s.url ? '<a class="btn primary" href="' + esc(s.url) + '" target="_blank" rel="noopener">Get tickets</a>' : "") +
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
  // After a re-render, keep keyboard focus on the poster that was just opened or closed.
  function focusPoster(i) { var el = document.querySelector('#grid button[data-p="' + i + '"]'); if (el) el.focus({ preventScroll: true }); }
  function measure() { document.documentElement.style.setProperty("--days-h", $("days").offsetHeight + "px"); }

  function wire() {
    document.addEventListener("click", function (e) {
      if (e.target.id === "backdrop") return closeSheet();
      var info = e.target.closest(".info");
      if (info && !e.target.closest("a")) { state.open = null; renderFilms(); focusPoster(+info.dataset.p); return; }
      var b = e.target.closest("button"); if (!b) return;
      if (b.dataset.p) { var p = +b.dataset.p; state.open = state.open === p ? null : p; renderFilms(); focusPoster(p); return; }
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
      if (b.id === "calToggle") {
        var opts = $("calOpts"), show = opts.hidden; opts.hidden = !show; b.setAttribute("aria-expanded", show);
        if (show) opts.querySelector("a").focus(); return;
      }
      if (b.dataset.d) { state.day = b.dataset.d; state.showEarlier = false; state.open = null; setMode(); renderDays(); renderAll(); toFilms(); return; }
      if (b.dataset.k) {
        var k = b.dataset.k; state.theaters.has(k) ? state.theaters.delete(k) : state.theaters.add(k); state.radius = null;
        saveTheaters(); renderAll(); return;
      }
      if (b.dataset.r) {
        state.radius = b.dataset.r; applyRadius(); pickShownTheaters(); saveTheaters(); renderAll(); return;
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
      if (state.open != null) { var p = state.open; state.open = null; renderFilms(); focusPoster(p); }
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
    window.addEventListener("resize", function () { measure(); clampVenues(); edges(); schedEdges(); });
    if (document.fonts) document.fonts.ready.then(function () { clampVenues(); edges(); schedEdges(); });   // re-measure in Archivo
    // A tab left open overnight would keep yesterday as "today": reload when the Denver date changes.
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState !== "visible") return;
      var d = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Denver" }).format(new Date());
      if (d !== NOW.day) location.reload();
    });
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
    })
    .catch(function (e) {
      $("grid").innerHTML = '<p class="empty">Couldn’t load showtimes (' + esc(e.message) + "). Try reloading the page.</p>";
    });
})();
