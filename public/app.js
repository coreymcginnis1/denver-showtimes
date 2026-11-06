/* Denver Showtimes: one day at a time.
   Poster cards for every film playing on the chosen day (times grouped by theater), plus that
   day's schedule in time order. Tap a time for tickets or to add it to Google / Outlook / .ics.
   Times are Denver wall-clock ("floating"): the ISO offset is ignored, so every viewer sees the
   time printed on the theater's own site. No dependencies. */
(function () {
  "use strict";

  // Short names for chips and rows; the full name is used in the sheet and calendar entries.
  var SHORT = { sie: "Sie FilmCenter", landmark: "Landmark Mayan", amc: "AMC 9+CO 10", regal_pavilions: "Regal Pavilions",
    alamo_sloans: "Alamo Sloans Lake", regal_colorado: "Regal Colorado Ctr", amc_westminster: "AMC Westminster",
    landmark_greenwood: "Landmark Greenwood", harkins_arvada: "Harkins Arvada", harkins_northfield: "Harkins Northfield" };
  var THEATER_SITES = [
    ["Sie FilmCenter", "https://www.denverfilm.org/"],
    ["Landmark Mayan", "https://www.landmarktheatres.com/our-locations/x02ak-landmark-mayan-theatre-denver/"],
    ["AMC 9+CO 10", "https://www.amctheatres.com/movie-theatres/denver/amc-9-co-10"],
    ["AMC Westminster", "https://www.amctheatres.com/movie-theatres/denver/amc-westminster-promenade-24"],
    ["Alamo Sloans Lake", "https://drafthouse.com/denver/theater/sloans-lake"],
    ["Regal Colorado Center", "https://www.regmovies.com/theatres/regal-ua-colorado-center-1308"],
    ["Regal Denver Pavilions", "https://www.regmovies.com/theatres/regal-ua-denver-pavilions-rpx-1315"],
    ["Landmark Greenwood Village", "https://www.landmarktheatres.com/our-locations/x0873-the-landmark-greenwood-village/"],
    ["Harkins Arvada", "https://www.harkins.com/theatres/arvada-14"],
    ["Harkins Northfield", "https://www.harkins.com/theatres/northfield-18"]
  ];
  var FMT_TAG = { "Premium Format": "Prem", "3D": "3D", "Scope": "Scope", "35mm": "35mm", "70mm": "70mm" };
  var SLOTS = [["Morning", "00:00"], ["Afternoon", "12:00"], ["Evening", "17:00"], ["Late", "21:00"]];

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
  var state = { day: null, q: "", sort: "new", kind: "all", showEarlier: false, theaters: null, zip: DEFAULT_ZIP, radius: null };

  // ---- Data ------------------------------------------------------------------

  function load(data) {
    D = data;
    theaters = data.theaters;
    var meta = data.film_meta || {}, index = {};
    films = data.films.map(function (t, i) {
      index[t] = i;
      var m = meta[t] || {};
      return { t: t, id: m.tmdb_id || null, rel: m.release || null, pop: m.popularity, va: m.vote_average, vc: m.vote_count || 0,
        indie: !!m.indie, intl: !!m.intl,
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
        end: e.end ? e.end.slice(0, 16) : null, fmt: x.fmt, scr: x.screen, url: x.ticketUrl, id: e.id });
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
      .filter(function (d) { return d >= NOW.day; });
    if (!days.length) days = Array.from(new Set(shows.map(function (s) { return s.d; }))).sort();
    state.day = days.indexOf(NOW.day) >= 0 ? NOW.day : days[0];

    var saved = store("dst-theaters");
    var valid = Array.isArray(saved) ? saved.filter(function (k) { return theaterOf(k); }) : [];
    state.theaters = new Set(valid.length ? valid : theaters.filter(function (t) { return t.default_on !== false; }).map(function (t) { return t.key; }));
  }

  // Repertory: the film first came out more than two years before it opened here (a revival).
  // Two years, not one: indie films often reach Denver a year or more after a festival premiere
  // (TMDB dates them by it). New releases (and events with no release date) are everything else.
  var REPERTORY_DAYS = 730;
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
  function dayShows(d, anyTheater) {
    var q = state.q.toLowerCase();
    return shows.filter(function (s) {
      var f = films[s.f];
      return (d === ALL ? days.indexOf(s.d) >= 0 && !isPast(s) : s.d === d) && (anyTheater || state.theaters.has(s.th)) && (!q || f.t.toLowerCase().indexOf(q) >= 0) &&
        (state.kind === "all" || (!f.event && (state.kind === "rep") === f.rep));
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

  function renderUpdated() {
    var g = new Date(D.generated_at);
    $("updated").textContent = "Updated " + g.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
      " · " + D.events.length.toLocaleString() + " showtimes";
    $("srcLinks").innerHTML = "Theater sites: " + THEATER_SITES.map(function (t) {
      return '<a href="' + t[1] + '" target="_blank" rel="noopener">' + esc(t[0]) + "</a>";
    }).join(" · ");
  }

  var ALL = "all";   // state.day for the "Next 2 weeks" view
  function shortDate(d) { return dateObj(d).toLocaleDateString("en-US", { month: "short", day: "numeric" }); }
  function dayName(d) { return relDay(d) || dateObj(d).toLocaleDateString("en-US", { weekday: "short" }) + " " + shortDate(d); }

  function renderDays() {
    $("days").innerHTML = '<button type="button" class="day rel span" data-d="' + ALL + '" aria-pressed="' + (state.day === ALL) + '">' +
      '<span class="dw">Next</span><span class="dn">2 weeks</span></button>' + days.map(function (d) {
      var rel = relDay(d), o = dateObj(d);
      return '<button type="button" class="day' + (rel ? " rel" : "") + '" data-d="' + d + '" aria-pressed="' + (d === state.day) + '">' +
        '<span class="dw">' + (rel || o.toLocaleDateString("en-US", { weekday: "short" })) + "</span>" +
        '<span class="dn">' + o.toLocaleDateString("en-US", { month: "short", day: "numeric" }) + "</span></button>";
    }).join("");
  }

  function renderTheaters() {
    var counts = {};
    dayShows(state.day, true).forEach(function (s) { counts[s.th] = (counts[s.th] || 0) + 1; });
    var near = theaters.slice().sort(function (a, b) { return (miles(a) || 0) - (miles(b) || 0); });
    $("theaters").innerHTML = near.map(function (t) {
      var mi = miles(t);
      return '<button type="button" class="chip" style="--c:' + t.color + '" data-k="' + t.key + '" aria-pressed="' + state.theaters.has(t.key) + '">' +
        '<span class="dot"></span>' + esc(tName(t.key)) + (mi != null ? ' <span class="mi">' + mi.toFixed(1) + " mi</span>" : "") +
        ' <span class="n">' + (counts[t.key] || 0) + "</span></button>";
    }).join("");
    document.querySelectorAll("[data-r]").forEach(function (x) { x.setAttribute("aria-pressed", String(x.dataset.r === String(state.radius))); });
  }

  // ---- Film cards ----------------------------------------------------------------

  function posterHTML(i, cls) {
    var f = films[i];
    if (!f.posters.length) return fallbackHTML(f);
    return '<img' + (cls ? ' class="' + cls + '"' : "") + ' src="' + esc(f.posters[0]) + '" data-f="' + i + '" data-n="0" alt="' +
      (cls ? "" : "Poster for " + esc(f.t)) + '" loading="lazy" decoding="async" referrerpolicy="no-referrer">';
  }
  function fallbackHTML(f) { return '<div class="fallback" aria-hidden="true">' + esc(f.t) + "<small>No poster</small></div>"; }

  // A broken poster tries the film's next image, then a typeset placeholder.
  document.addEventListener("error", function (e) {
    var img = e.target;
    if (!img || img.tagName !== "IMG" || img.dataset.f === undefined) return;
    var f = films[+img.dataset.f], n = +img.dataset.n + 1;
    if (n < f.posters.length) { img.dataset.n = n; img.src = f.posters[n]; return; }
    if (img.classList.contains("th")) { img.removeAttribute("src"); img.dataset.f = ""; return; }
    img.outerHTML = fallbackHTML(f);
  }, true);

  function sortFilms(ids) {
    var key = {
      // Newest: new releases by Denver release week (latest first, upcoming on top) and, within a
      // week, by Trending; then repertory by original release; special events last.
      new: function (f) {
        if (f.event) return null;   // events sort after every film
        // A week is never more than 6.048e8 ms apart from the next, and TMDB popularity stays far
        // below that, so adding it orders films within a week without crossing weeks.
        if (!f.rep) return f.opened ? 1e13 + Date.parse(releaseWeek(f.opened)) + Math.min(f.pop || 0, 1e7) : null;
        var r = f.rel || (f.year ? f.year + "-07-01" : null); return r ? Date.parse(r) : null;
      },
      pop: function (f) { return f.id ? f.pop : null; }
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
    var ids = sortFilms(Array.from(byFilm.keys())), rel = relDay(state.day);

    var all = state.day === ALL;
    // Searching also finds a film beyond the chosen theaters/day ("Fjord" only at AMC Westminster):
    // those matches follow the normal results as compact two-week cards.
    var elsewhere = new Map();
    if (state.q) {
      var q = state.q.toLowerCase();
      shows.forEach(function (s) {
        var f = films[s.f];
        if (byFilm.has(s.f) || days.indexOf(s.d) < 0 || isPast(s) || f.t.toLowerCase().indexOf(q) < 0) return;
        if (state.kind !== "all" && (f.event || (state.kind === "rep") !== f.rep)) return;
        if (!elsewhere.has(s.f)) elsewhere.set(s.f, []); elsewhere.get(s.f).push(s);
      });
    }
    var extraIds = sortFilms(Array.from(elsewhere.keys()));
    $("filmsH").textContent = all ? "Playing the next two weeks" : "Playing " + (rel ? rel.toLowerCase() : longDate(state.day));
    $("filmsSub").textContent = (all ? shortDate(days[0]) + "–" + shortDate(days[days.length - 1]) + " · "
      : rel ? longDate(state.day) + " · " : "") + ids.length + " film" + (ids.length === 1 ? "" : "s") +
      " · " + state.theaters.size + " theater" + (state.theaters.size === 1 ? "" : "s");

    if (!ids.length && !extraIds.length) {
      $("grid").innerHTML = '<p class="empty">' + (state.theaters.size
        ? "Nothing matches" + (all ? "" : " on this day") + ". Try " + (all ? "" : "another day, ") + "more theaters, or clear the search."
        : "Pick at least one theater above to see films.") + "</p>";
      return;
    }
    var cardHTML = function (i, other) {   // other: a match from beyond the selected theaters/day
      var f = films[i], list = (other ? elsewhere : byFilm).get(i), venues = new Map(), asSpan = all || !!other;
      list.sort(function (a, b) { return (a.d + (a.hm || "")).localeCompare(b.d + (b.hm || "")); })
        .forEach(function (s) { if (!venues.has(s.th)) venues.set(s.th, []); venues.get(s.th).push(s); });
      var fmts = Array.from(new Set(list.map(function (s) { return s.fmt === "Premium Format" ? "Premium" : s.fmt; }).filter(Boolean)));
      var meta = [f.year ? "<span>" + f.year + "</span>" : "", f.rating ? "<span>" + esc(f.rating) + "</span>" : "",
        f.runtime ? "<span>" + runtime(f.runtime) + "</span>" : ""]
        .concat(fmts.map(function (x) { return '<span class="tag">' + esc(x) + "</span>"; })).join("");
      var since = f.opened ? dayDiff(f.opened, asSpan ? days[0] : state.day) : null;
      var fresh = f.rep || f.event || since == null ? "" : since < 0 ? "Opens " + shortDate(f.opened)
        : since === 0 ? "Opening day" : since <= 6 ? "New this week" : "";
      if (fresh) meta += '<span class="tag fresh">' + fresh + "</span>";
      // "Indie" and "International" tags are on hold (Nov 2026): the Indie guess (TMDB lists
      // producers, not distributors) wasn't reliable, and Corey wants both or neither. The data
      // (film_meta.indie / .intl) is still in data.json.
      var order = theaters.map(function (t) { return t.key; });
      var vhtml = Array.from(venues.entries()).sort(function (a, b) { return order.indexOf(a[0]) - order.indexOf(b[0]); }).map(function (e) {
        var t = theaterOf(e[0]) || { color: "#888" };
        if (asSpan) {   // one line per theater: when it plays, how often, and the next showing
          var first = e[1][0], last = e[1][e[1].length - 1], n = e[1].length;
          var span = first.d === last.d ? dayName(first.d) : shortDate(first.d) + "–" + shortDate(last.d);
          return '<div class="venue" style="--c:' + t.color + '"><div class="vn"><i></i>' + esc(tName(e[0])) + "</div>" +
            '<div class="span-line">' + span + " · " + n + " showing" + (n === 1 ? "" : "s") + "</div>" +
            '<div class="times"><button type="button" class="time next" data-i="' + shows.indexOf(first) + '" aria-label="' +
            esc(f.t) + ", next showing " + dayName(first.d) + " " + (first.hm ? longTime(first.hm) : "") + ", " + esc(t.name || "") + '"><span class="ap">Next</span> ' +
            dayName(first.d) + (first.hm ? " · " + timeHTML(first.hm) : "") + "</button></div></div>";
        }
        return '<div class="venue" style="--c:' + t.color + '"><div class="vn"><i></i>' + esc(tName(e[0])) + '</div><div class="times">' +
          e[1].map(function (s) {
            var tag = FMT_TAG[s.fmt] ? "<sup>" + FMT_TAG[s.fmt] + "</sup>" : "";
            var label = s.hm ? timeHTML(s.hm) : "Times vary";
            return '<button type="button" class="time' + (isPast(s) ? " past" : "") + '" data-i="' + shows.indexOf(s) + '" aria-label="' +
              esc(f.t) + ", " + (s.hm ? longTime(s.hm) : "times vary") + ", " + esc(t.name || "") + '">' + label + tag + "</button>";
          }).join("") + "</div></div>";
      }).join("");
      return '<article class="card"><div class="poster">' + posterHTML(i) +
        "</div>" +
        '<h3 class="title">' + esc(f.t) + "</h3>" + (meta ? '<div class="meta">' + meta + "</div>" : "") +
        '<div class="venues">' + vhtml + "</div>" +
        '<button type="button" class="more" hidden>Show all times</button>' +
        (f.id ? '<a class="lb" href="https://letterboxd.com/tmdb/' + f.id + '/" target="_blank" rel="noopener">View on Letterboxd</a>' : "") +
        "</article>";
    };
    if (all) {   // two groups: what you can see now (by the chosen sort), then openings, soonest first
      var soon = ids.filter(function (i) { return films[i].opened && films[i].opened > days[0] && !films[i].rep; });
      var now = ids.filter(function (i) { return soon.indexOf(i) < 0; });
      soon.sort(function (a, b) { return films[a].opened.localeCompare(films[b].opened) || films[a].t.localeCompare(films[b].t); });
      $("grid").innerHTML = (now.length ? '<h3 class="group">Now playing <span>' + now.length + "</span></h3>" +
          '<div class="grid">' + now.map(function (i) { return cardHTML(i); }).join("") + "</div>" : "") +
        (soon.length ? '<h3 class="group">Opening soon <span>' + soon.length + "</span></h3>" +
          '<div class="grid">' + soon.map(function (i) { return cardHTML(i); }).join("") + "</div>" : "");
    } else {
      $("grid").innerHTML = ids.length ? '<div class="grid">' + ids.map(function (i) { return cardHTML(i); }).join("") + "</div>"
        : '<p class="empty">No match at these theaters' + (all ? "" : " on this day") + ".</p>";
    }
    if (extraIds.length) {
      $("grid").innerHTML += '<h3 class="group">Also playing elsewhere <span>' + extraIds.length + "</span></h3>" +
        '<p class="group-note">Other theaters or days in the next two weeks.</p>' +
        '<div class="grid">' + extraIds.map(function (i) { return cardHTML(i, true); }).join("") + "</div>";
    }
    clampVenues();
  }

  // Several theaters can make a card's times run far past its poster: clamp the list and offer
  // "Show all times" only where it actually overflows (checked after layout).
  function clampVenues() {
    document.querySelectorAll("#grid .card").forEach(function (card) {
      var v = card.querySelector(".venues"), btn = card.querySelector(".more");
      if (!v || !btn || card.classList.contains("open")) return;
      v.classList.add("clamp");
      var over = v.scrollHeight > v.clientHeight + 4;
      if (!over) v.classList.remove("clamp");
      btn.hidden = !over;
      if (over) {
        var n = v.querySelectorAll(".venue").length;
        btn.textContent = n > 1 ? "Show all " + n + " theaters" : "Show all times";
      }
    });
  }

  // ---- Schedule --------------------------------------------------------------------

  function renderSchedule() {
    var ds = dayShows(state.day).filter(function (s) { return s.hm; })
      .sort(function (a, b) { return a.hm.localeCompare(b.hm) || films[a.f].t.localeCompare(films[b.f].t); });
    var past = ds.filter(isPast), shown = state.showEarlier ? ds : ds.filter(function (s) { return !isPast(s); });
    if (!ds.length) {
      $("sched").innerHTML = '<p class="empty">' + "No showtimes match." + "</p>";
      return;
    }
    var html = shown.length ? "" : '<p class="empty">Everything has started for today.</p>';
    SLOTS.forEach(function (sl, n) {
      var end = n + 1 < SLOTS.length ? SLOTS[n + 1][1] : "99";
      var rows = shown.filter(function (s) { return s.hm >= sl[1] && s.hm < end; });
      if (!rows.length) return;
      html += '<div class="slot"><span>' + sl[0] + "</span><span>" + rows.length + "</span></div>" + rows.map(function (s) {
        var f = films[s.f], t = theaterOf(s.th) || { color: "#888" }, extra = [s.fmt === "Premium Format" ? "Premium" : s.fmt, s.scr].filter(Boolean).join(" · ");
        return '<button type="button" class="row' + (isPast(s) ? " past" : "") + '" data-i="' + shows.indexOf(s) + '" style="--c:' + t.color + '">' +
          '<span class="t">' + timeHTML(s.hm) + "</span>" + (f.posters.length ? posterHTML(s.f, "th") : '<span class="th"></span>') +
          '<span class="f"><b>' + esc(f.t) + "</b><span><i></i>" + esc(tName(s.th)) + (extra ? " · " + esc(extra) : "") + "</span></span></button>";
      }).join("");
    });
    if (past.length) html += '<button type="button" class="earlier" id="earlier">' + (state.showEarlier ? "Hide " : "Show ") + past.length + " earlier today</button>";
    $("sched").innerHTML = html;
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
    var where = [t.name, s.scr, s.fmt].filter(Boolean).join(" · "), links = s.hm ? calendarLinks(s) : null;
    icsUrl = links && links.ics;
    var when = dateObj(s.d).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }) +
      (s.hm ? " · " + timeHTML(s.hm) + "–" + timeHTML(links.end.hm) : " · times vary");
    $("backdrop").innerHTML = '<div class="sheet" role="dialog" aria-modal="true" aria-labelledby="sheetT">' +
      (f.posters.length ? posterHTML(s.f, "sheet-poster") : '<div class="ph"></div>') +
      '<div><h3 id="sheetT">' + esc(f.t) + '</h3><div class="when">' + when + "</div>" +
      '<div class="where">' + esc(where) + (s.hm && !s.end && !f.runtime ? " · runtime unknown, 2h assumed" : "") + "</div></div>" +
      '<div class="actions">' + (s.url ? '<a class="btn primary" href="' + esc(s.url) + '" target="_blank" rel="noopener">Get tickets</a>' : "") +
      (links ? '<div class="btn-row three"><a class="btn" href="' + esc(links.google) + '" target="_blank" rel="noopener">Google</a>' +
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

  function setMode() {   // the two-week view has no schedule column
    var all = state.day === ALL;
    $("layout").dataset.mode = all ? "span" : "day";
    var seg = document.querySelector(".seg"); if (seg) seg.hidden = all;
    if (all) {
      $("layout").dataset.view = "films";
      document.querySelectorAll("[data-v]").forEach(function (x) { x.setAttribute("aria-pressed", x.dataset.v === "films"); });
    }
  }
  function renderAll() { renderTheaters(); renderFilms(); if (state.day !== ALL) renderSchedule(); }
  function measure() { document.documentElement.style.setProperty("--bar-h", $("bar").offsetHeight + "px"); }

  function wire() {
    document.addEventListener("click", function (e) {
      if (e.target.id === "backdrop") return closeSheet();
      var b = e.target.closest("button"); if (!b) return;
      if (b.id === "closeSheet") return closeSheet();
      if (b.dataset.d) { state.day = b.dataset.d; state.showEarlier = false; setMode(); renderDays(); renderAll(); window.scrollTo({ top: 0 }); return; }
      if (b.dataset.k) {
        var k = b.dataset.k; state.theaters.has(k) ? state.theaters.delete(k) : state.theaters.add(k); state.radius = null;
        store("dst-theaters", Array.from(state.theaters)); renderAll(); return;
      }
      if (b.dataset.r) {
        state.radius = b.dataset.r; applyRadius(); store("dst-theaters", Array.from(state.theaters)); renderAll(); return;
      }
      if (b.dataset.kind) {
        state.kind = b.dataset.kind;
        document.querySelectorAll("[data-kind]").forEach(function (x) { x.setAttribute("aria-pressed", x === b); });
        renderAll(); return;
      }
      if (b.dataset.s) {
        state.sort = b.dataset.s;
        document.querySelectorAll("[data-s]").forEach(function (x) { x.setAttribute("aria-pressed", x === b); });
        renderFilms(); return;
      }
      if (b.dataset.v) {
        $("layout").dataset.view = b.dataset.v;
        document.querySelectorAll("[data-v]").forEach(function (x) { x.setAttribute("aria-pressed", x === b); });
        return;
      }
      if (b.classList.contains("more")) {
        var card = b.closest(".card"); card.classList.add("open");
        card.querySelector(".venues").classList.remove("clamp"); b.hidden = true; return;
      }
      if (b.id === "earlier") { state.showEarlier = !state.showEarlier; renderSchedule(); return; }
      if (b.dataset.i) openSheet(+b.dataset.i);
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !$("backdrop").hidden) closeSheet(); });
    $("q").addEventListener("input", function (e) { state.q = e.target.value.trim(); renderAll(); });
    $("zip").addEventListener("input", function (e) {
      var z = e.target.value.replace(/\D/g, "").slice(0, 5);
      if (z !== e.target.value) e.target.value = z;
      var ok = z.length === 5 && ZIPS[z];
      $("zipNote").hidden = !(z.length === 5 && !ok);
      if (ok) { state.zip = z; applyRadius(); renderAll(); }
    });
    window.addEventListener("resize", function () { measure(); clampVenues(); });
  }

  var zipTable = fetch("zips.json").then(function (r) { return r.ok ? r.json() : {}; }).catch(function () { return {}; });
  fetch("data.json?_=" + Date.now(), { cache: "no-store" })
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (data) { return zipTable.then(function (z) { ZIPS = z; return data; }); })
    .then(function (data) {
      load(data); wire(); setMode(); renderUpdated(); renderDays(); renderAll(); measure();
      var sel = $("days").querySelector('[aria-pressed="true"]'); if (sel) sel.scrollIntoView({ block: "nearest", inline: "center" });
    })
    .catch(function (e) {
      $("grid").innerHTML = '<p class="empty">Couldn’t load showtimes (' + esc(e.message) + "). Try reloading the page.</p>";
    });
})();
