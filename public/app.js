/* Denver showtimes interactive calendar.
   Loads data.json, lets users toggle theaters/films, and add a screening to
   their own calendar (Google / Outlook / .ics). Times are shown as Denver
   wall-clock for every viewer by stripping the offset before FullCalendar sees them. */
(function () {
  "use strict";

  var DATA = null;
  var CAL = null;
  var enabledTheaters = new Set();
  var enabledFilms = new Set();
  var query = "";

  function $(id) { return document.getElementById(id); }
  function stripTZ(iso) { return iso.replace(/([+-]\d{2}:\d{2}|Z)$/, ""); }

  function init() {
    fetch("data.json?_=" + Date.now())
      .then(function (r) { return r.json(); })
      .then(function (data) {
        DATA = data;
        enabledTheaters = new Set(data.theaters.map(function (t) { return t.key; }));
        enabledFilms = new Set(data.films);
        renderUpdated();
        renderTheaterChips();
        renderFilmList();
        renderSourceLinks();
        initCalendar();
      })
      .catch(function (e) {
        $("calendar").innerHTML = "<p style='color:#9a3412'>Couldn't load showtimes: " + e + "</p>";
      });
  }

  function theaterMeta(key) {
    return DATA.theaters.find(function (t) { return t.key === key; }) || { name: key, color: "#888" };
  }

  function passes(e) {
    var p = e.extendedProps;
    if (!enabledTheaters.has(p.theater)) return false;
    if (!enabledFilms.has(e.title)) return false;
    if (query && e.title.toLowerCase().indexOf(query) === -1) return false;
    return true;
  }

  function forCalendar(e) {
    return {
      id: e.id,
      title: e.title,
      allDay: e.allDay,
      start: stripTZ(e.start),
      end: e.end ? stripTZ(e.end) : undefined,
      backgroundColor: e.backgroundColor,
      borderColor: e.borderColor,
      extendedProps: Object.assign({}, e.extendedProps, { _start: e.start, _end: e.end || null }),
    };
  }

  function filteredEvents() {
    return DATA.events.filter(passes).map(forCalendar);
  }

  // ---- Controls ------------------------------------------------------------

  function renderUpdated() {
    var d = new Date(DATA.generated_at);
    $("updated").textContent = "Updated " + d.toLocaleString("en-US", {
      dateStyle: "medium", timeStyle: "short",
    }) + " · " + DATA.events.length + " screenings";
  }

  function countByTheater(key) {
    return DATA.events.reduce(function (n, e) {
      return n + (e.extendedProps.theater === key ? 1 : 0);
    }, 0);
  }

  function renderTheaterChips() {
    var box = $("theaterChips");
    box.innerHTML = "";
    DATA.theaters.forEach(function (t) {
      var chip = document.createElement("span");
      chip.className = "chip";
      chip.innerHTML = '<span class="dot" style="background:' + t.color + '"></span>' +
        t.name + ' <span class="count">' + countByTheater(t.key) + "</span>";
      chip.addEventListener("click", function () {
        if (enabledTheaters.has(t.key)) enabledTheaters.delete(t.key);
        else enabledTheaters.add(t.key);
        chip.classList.toggle("off", !enabledTheaters.has(t.key));
        refresh();
      });
      box.appendChild(chip);
    });
  }

  function renderFilmList() {
    var list = $("filmList");
    list.innerHTML = "";
    DATA.films.forEach(function (title) {
      var label = document.createElement("label");
      label.dataset.title = title.toLowerCase();
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = enabledFilms.has(title);
      cb.addEventListener("change", function () {
        if (cb.checked) enabledFilms.add(title); else enabledFilms.delete(title);
        refresh();
      });
      label.appendChild(cb);
      label.appendChild(document.createTextNode(" " + title));
      list.appendChild(label);
    });
  }

  function applySearch() {
    var any = false;
    $("filmList").querySelectorAll("label").forEach(function (l) {
      var hit = !query || l.dataset.title.indexOf(query) !== -1;
      l.classList.toggle("hidden", !hit);
      if (hit) any = true;
    });
    var existing = $("filmList").querySelector(".empty");
    if (existing) existing.remove();
    if (!any) {
      var e = document.createElement("div");
      e.className = "empty";
      e.textContent = "No films match “" + query + "”";
      $("filmList").appendChild(e);
    }
  }

  function wireControls() {
    $("filmSearch").addEventListener("input", function (ev) {
      query = ev.target.value.trim().toLowerCase();
      applySearch();
      refresh();
    });
    $("selectAll").addEventListener("click", function () {
      DATA.films.forEach(function (f) { enabledFilms.add(f); });
      syncFilmChecks();
      refresh();
    });
    $("clearAll").addEventListener("click", function () {
      enabledFilms.clear();
      syncFilmChecks();
      refresh();
    });
  }

  function syncFilmChecks() {
    $("filmList").querySelectorAll("label").forEach(function (l) {
      var cb = l.querySelector("input");
      cb.checked = enabledFilms.has(l.childNodes[1].textContent.trim());
    });
  }

  function renderSourceLinks() {
    $("srcLinks").innerHTML =
      '<a href="https://denverfilm.org/sie-filmcenter/" target="_blank" rel="noopener">Sie FilmCenter</a> · ' +
      '<a href="https://www.landmarktheatres.com/theaters/x02ak-landmark-mayan-theatre-denver/" target="_blank" rel="noopener">Landmark Mayan</a> · ' +
      '<a href="https://www.amctheatres.com/movie-theatres/denver/amc-9-co-10/showtimes" target="_blank" rel="noopener">AMC 9+CO 10</a>';
  }

  // ---- Calendar ------------------------------------------------------------

  function initCalendar() {
    wireControls();
    CAL = new FullCalendar.Calendar($("calendar"), {
      initialView: window.innerWidth < 760 ? "listWeek" : "dayGridMonth",
      headerToolbar: {
        left: "prev,next today",
        center: "title",
        right: "dayGridMonth,timeGridWeek,listWeek",
      },
      height: "auto",
      nowIndicator: true,
      displayEventEnd: false,
      eventTimeFormat: { hour: "numeric", minute: "2-digit", meridiem: "short" },
      noEventsContent: "No screenings match your filters",
      events: function (info, success) { success(filteredEvents()); },
      eventClick: function (arg) { arg.jsEvent.preventDefault(); openModal(arg.event); },
    });
    CAL.render();
  }

  function refresh() { if (CAL) CAL.refetchEvents(); }

  // ---- Modal + add-to-calendar --------------------------------------------

  function openModal(ev) {
    var p = ev.extendedProps;
    var m = theaterMeta(p.theater);
    var when = ev.allDay
      ? new Date(p._start).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })
      : new Date(p._start).toLocaleString("en-US", { weekday: "long", month: "long", day: "numeric", hour: "numeric", minute: "2-digit" });

    var meta = [];
    if (p.fmt) meta.push(p.fmt);
    if (p.runtime) meta.push(Math.floor(p.runtime / 60) + "h " + (p.runtime % 60) + "m");
    if (p.rating) meta.push(p.rating);
    if (p.year) meta.push(p.year);
    if (p.director) meta.push("Dir. " + p.director);

    var html = '<div class="head">';
    if (p.poster) html += '<img class="poster" src="' + p.poster + '" alt="" />';
    html += '<div style="flex:1"><span class="theater-badge" style="background:' + m.color + '">' +
      esc(m.name) + '</span><h2>' + esc(ev.title) + '</h2>' +
      '<div class="when">' + esc(when) + '</div>';
    if (meta.length) html += '<div class="meta">' + esc(meta.join(" · ")) + '</div>';
    html += '</div><button class="close" aria-label="Close">&times;</button></div>';

    html += '<div class="body">';
    if (ev.allDay && p.note) html += '<div class="note">' + esc(p.note) + '</div>';
    html += '<div class="actions">';
    if (p.ticketUrl) html += '<a class="primary" href="' + p.ticketUrl + '" target="_blank" rel="noopener">Get tickets ↗</a>';
    html += '</div>';

    if (!ev.allDay) {
      var ics = URL.createObjectURL(icsBlob(ev));
      html += '<div class="addcal-label">Add this showtime to your calendar</div><div class="actions">' +
        '<a href="' + googleUrl(ev) + '" target="_blank" rel="noopener">Google</a>' +
        '<a href="' + outlookUrl(ev) + '" target="_blank" rel="noopener">Outlook</a>' +
        '<a href="' + ics + '" download="' + slug(ev.title) + '.ics">Apple / .ics</a>' +
        '</div>';
    }
    html += '</div>';

    var modal = $("modal");
    modal.innerHTML = html;
    modal.querySelector(".close").addEventListener("click", closeModal);
    $("modalBackdrop").classList.add("open");
  }

  function closeModal() { $("modalBackdrop").classList.remove("open"); }

  $("modalBackdrop") && $("modalBackdrop").addEventListener("click", function (e) {
    if (e.target === $("modalBackdrop")) closeModal();
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });

  function pad(n) { return String(n).padStart(2, "0"); }
  function toUTC(iso) {
    var d = new Date(iso);
    return d.getUTCFullYear() + pad(d.getUTCMonth() + 1) + pad(d.getUTCDate()) + "T" +
      pad(d.getUTCHours()) + pad(d.getUTCMinutes()) + pad(d.getUTCSeconds()) + "Z";
  }
  function esc(s) { var d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; }
  function slug(s) { return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "showtime"; }

  function descText(ev) {
    var p = ev.extendedProps, parts = [];
    if (p.fmt) parts.push(p.fmt);
    if (p.ticketUrl) parts.push("Tickets: " + p.ticketUrl);
    return parts.join("\n");
  }

  function dateRange(ev) {
    var s = ev.extendedProps._start;
    var e = ev.extendedProps._end || s;
    return toUTC(s) + "/" + toUTC(e);
  }

  function googleUrl(ev) {
    var p = ev.extendedProps;
    return "https://calendar.google.com/calendar/render?action=TEMPLATE" +
      "&text=" + encodeURIComponent(ev.title + " — " + p.theaterName) +
      "&dates=" + dateRange(ev) +
      "&details=" + encodeURIComponent(descText(ev)) +
      "&location=" + encodeURIComponent(p.theaterName);
  }

  function outlookUrl(ev) {
    var p = ev.extendedProps;
    return "https://outlook.live.com/calendar/0/deeplink/compose?path=/calendar/action/compose&rru=addevent" +
      "&subject=" + encodeURIComponent(ev.title + " — " + p.theaterName) +
      "&startdt=" + encodeURIComponent(p._start) +
      "&enddt=" + encodeURIComponent(p._end || p._start) +
      "&location=" + encodeURIComponent(p.theaterName) +
      "&body=" + encodeURIComponent(descText(ev));
  }

  function icsEsc(s) { return String(s).replace(/([,;\\])/g, "\\$1").replace(/\n/g, "\\n"); }
  function icsBlob(ev) {
    var p = ev.extendedProps;
    var lines = [
      "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//denver-showtimes//EN", "CALSCALE:GREGORIAN",
      "BEGIN:VEVENT",
      "UID:" + ev.id + "@denver-showtimes",
      "DTSTAMP:" + toUTC(new Date().toISOString()),
      "DTSTART:" + toUTC(p._start),
      "DTEND:" + toUTC(p._end || p._start),
      "SUMMARY:" + icsEsc(ev.title + " — " + p.theaterName),
      "LOCATION:" + icsEsc(p.theaterName),
      "DESCRIPTION:" + icsEsc(descText(ev)),
      "END:VEVENT", "END:VCALENDAR",
    ];
    return new Blob([lines.join("\r\n")], { type: "text/calendar;charset=utf-8" });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
