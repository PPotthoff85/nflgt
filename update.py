#!/usr/bin/env python3
"""Holt abgeschlossene Spieltage von Sleeper und schreibt sie in index.html (const D = {...}).
Läuft per GitHub Actions jeden Dienstag früh. Nur Python-Standardbibliothek."""
import json, re, sys, urllib.request

LEAGUE = "1389357715347750912"
SEASON = 2026
REG_WEEKS = 14          # Hauptrunde: Rangpunkte nur Woche 1-14
FILE = "index.html"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "nflgt-portal"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def sleeper(path):
    return get("https://api.sleeper.app/v1/" + path)

html = open(FILE, encoding="utf-8").read()
m = re.search(r"const D = (\{.*?\});\n", html, re.S)
if not m:
    sys.exit("const D nicht gefunden")
D = json.loads(m.group(1))

# Sleeper-Anzeigename -> Teamschlüssel im Portal (über "owner", robust gegen Umbenennungen)
by_owner = {v["owner"]: k for k, v in D["teams"].items()}
users = sleeper(f"league/{LEAGUE}/users")
rosters = sleeper(f"league/{LEAGUE}/rosters")
uname = {u["user_id"]: u["display_name"] for u in users}
team_of = {}
for r in rosters:
    dn = uname.get(r["owner_id"])
    if dn not in by_owner:
        sys.exit(f"Unbekannter Besitzer {dn}: bitte in D.teams eintragen")
    team_of[r["roster_id"]] = by_owner[dn]

sched = get(f"https://api.sleeper.com/schedule/nfl/regular/{SEASON}")
def complete(w):
    g = [x for x in sched if x.get("week") == w]
    return bool(g) and all(x.get("status") == "complete" for x in g)

done = [w for w in range(1, REG_WEEKS + 1) if complete(w)]
have = sorted(int(k) for k in D["weeks"])
todo = [w for w in done if str(w) not in D["weeks"]]
if have and have[-1] in done:
    todo = sorted(set(todo + [have[-1]]))      # letzte Woche erneut (Stat-Korrekturen)
print("abgeschlossen:", done, "| vorhanden:", have, "| berechne:", todo)
if not todo and D.get("live") is None:
    print("nichts zu tun"); sys.exit(0)

players = get("https://api.sleeper.app/v1/players/nfl") if todo else {}
def pos(pid):
    p = players.get(pid)
    if p and p.get("position"):
        return p["position"]
    return "DEF" if not pid.isdigit() else "?"

for w in todo:
    mt = sleeper(f"league/{LEAGUE}/matchups/{w}")
    pr = get(f"https://api.sleeper.com/projections/nfl/{SEASON}/{w}?season_type=regular"
             "&position[]=QB&position[]=RB&position[]=WR&position[]=TE&position[]=DEF")
    proj = {p["player_id"]: (p.get("stats") or {}).get("pts_half_ppr") or 0 for p in pr}
    old = {r["team"]: r for r in D["weeks"].get(str(w), [])}
    rows = []
    for x in mt:
        pp = x.get("players_points") or {}
        used, opt = set(), 0.0
        for position, n in (("QB", 1), ("RB", 2), ("WR", 2), ("TE", 1), ("DEF", 1)):
            cand = sorted(((pp.get(i, 0), i) for i in x["players"] if pos(i) == position), reverse=True)[:n]
            for v, i in cand:
                used.add(i); opt += v
        flex = sorted((pp.get(i, 0) for i in x["players"] if pos(i) in ("RB", "WR", "TE") and i not in used), reverse=True)[:2]
        opt += sum(flex)
        team = team_of[x["roster_id"]]
        projected = old[team]["proj"] if team in old else round(sum(proj.get(i, 0) for i in x["starters"]), 2)
        rows.append({"team": team, "pts": round(x["points"], 2), "proj": projected,
                     "opt": round(opt, 2), "bench": round(sum(pp.values()) - x["points"], 2)})
    D["weeks"][str(w)] = rows
    print(f"Woche {w}:", ", ".join(f"{r['team']} {r['pts']}" for r in sorted(rows, key=lambda r: -r["pts"])))

D["live"] = None
new = html[:m.start(1)] + json.dumps(D, ensure_ascii=False) + html[m.end(1):]
if new != html:
    open(FILE, "w", encoding="utf-8").write(new)
    print("index.html aktualisiert")
else:
    print("keine Änderung")
