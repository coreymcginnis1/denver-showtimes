"""TEST ONLY (draft PR #21): how many current films have a Rotten Tomatoes / Metacritic number in
their English Wikipedia article. Finds each article by TMDB id on Wikidata (P4947), reads the
wikitext 50 pages a request, and looks for the {{Rotten Tomatoes prose}} / {{Metacritic film
prose}} templates or the usual sentences. Prints coverage by how long a film has been open."""
import json, re, sys, time, urllib.parse, urllib.request
from collections import defaultdict
from datetime import date

UA = {"User-Agent": "denver-showtimes-bot/1.0 (https://coreymcginnis1.github.io/denver-showtimes/)"}


def get(url):
    for i in range(3):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))
        except Exception as e:
            print("retry", url[:80], e); time.sleep(5)
    return {}


d = json.load(open(sys.argv[1]))
today = date.fromisoformat(d["generated_at"][:10])
films = {}
for t, m in d["film_meta"].items():
    if not m.get("tmdb_id"):
        continue
    rel, op = m.get("release"), d.get("openings", {}).get(t)
    rep = bool(rel and op and (date.fromisoformat(op) - date.fromisoformat(rel[:10])).days > 730)
    films[str(m["tmdb_id"])] = dict(title=t, rep=rep, days=(today - date.fromisoformat(op)).days if op else None)

ids = list(films)
art = {}
for i in range(0, len(ids), 150):
    q = """SELECT ?tmdb ?a WHERE { VALUES ?tmdb { %s } ?f wdt:P4947 ?tmdb .
           ?a schema:about ?f ; schema:isPartOf <https://en.wikipedia.org/> . }""" % " ".join('"%s"' % x for x in ids[i:i + 150])
    for r in get("https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(q)).get("results", {}).get("bindings", []):
        art[r["tmdb"]["value"]] = urllib.parse.unquote(r["a"]["value"].rsplit("/", 1)[1]).replace("_", " ")

RT = [re.compile(r"\{\{\s*Rotten Tomatoes prose\s*\|\s*(?:1\s*=\s*)?(\d{1,3})", re.I),
      re.compile(r"(\d{1,3})%\s+of\s+[\d,]+\s+critics'?\s*(?:&#39;)?\s*reviews\s+are\s+positive", re.I),
      re.compile(r"approval rating of (\d{1,3})%", re.I)]
MC = [re.compile(r"\{\{\s*Metacritic (?:film )?prose\s*\|\s*(?:1\s*=\s*)?(\d{1,3})", re.I),
      re.compile(r"(?:weighted )?average score of (\d{1,3}) out of 100", re.I)]
found = {}
titles = list(art.items())
for i in range(0, len(titles), 50):
    chunk = titles[i:i + 50]
    url = ("https://en.wikipedia.org/w/api.php?action=query&format=json&formatversion=2&redirects=1"
           "&prop=revisions&rvprop=content&rvslots=main&titles=" + urllib.parse.quote("|".join(a for _, a in chunk)))
    data = get(url).get("query", {})
    norm = {x["from"]: x["to"] for x in data.get("normalized", []) + data.get("redirects", [])}
    text = {p["title"]: p.get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("content", "") for p in data.get("pages", [])}
    for tid, a in chunk:
        t = text.get(norm.get(norm.get(a, a), norm.get(a, a)), "")
        rt = next((m.group(1) for r in RT for m in [r.search(t)] if m), None)
        mc = next((m.group(1) for r in MC for m in [r.search(t)] if m), None)
        found[tid] = (rt, mc)
    time.sleep(1)


def bucket(f):
    if f["rep"]:
        return "repertory"
    if f["days"] is None:
        return "new, no opening"
    if f["days"] < 0:
        return "new, not open yet"
    return "new, open 0-14 days" if f["days"] <= 14 else ("new, open 15-60 days" if f["days"] <= 60 else "new, open 60+ days")


agg = defaultdict(lambda: [0, 0, 0, 0])
for tid, f in films.items():
    b = bucket(f); rt, mc = found.get(tid, (None, None))
    agg[b][0] += 1; agg[b][1] += tid in art; agg[b][2] += rt is not None; agg[b][3] += mc is not None
print("\nCRITICS | group | films | has enwiki article | RT in article | MC in article")
for b, (n, a, rt, mc) in sorted(agg.items()):
    print(f"CRITICS | {b} | {n} | {a} | {rt} | {mc}")
for tid, f in sorted(films.items(), key=lambda x: (x[1]["days"] is None, x[1]["days"] or 0)):
    if not f["rep"] and f["days"] is not None and 0 <= f["days"] <= 60:
        rt, mc = found.get(tid, (None, None))
        print(f"CRITICS-FILM | {f['title']} | day {f['days']} | article {'yes' if tid in art else 'no'} | RT {rt or ''} | MC {mc or ''}")
