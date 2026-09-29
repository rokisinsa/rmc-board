"""LiveScore公開APIの試合別エンドポイント（H2H・直近・順位表）が取れるかを確かめる（data/probe/livescore.json）。"""
import gzip, json, os, time, urllib.request
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Accept-Encoding": "gzip"}
B = "https://prod-public-api.livescore.com/v1/api/app"
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30) as r:
            b = r.read()
            if r.headers.get("Content-Encoding") == "gzip": b = gzip.decompress(b)
            return r.status, b.decode("utf-8", "replace")
    except Exception as e:
        return str(e)[:120], ""
D = time.strftime("%Y%m%d", time.gmtime(time.time() + 9 * 3600 + 86400))
code, txt = get(f"{B}/date/soccer/{D}/9?countryCode=JP&locale=en&MD=1")
day = json.loads(txt)
ev = []
for st in day["Stages"]:
    for e in st.get("Events", []):
        ev.append((st, e))
out = dict(day_code=code, n_stages=len(day["Stages"]), n_events=len(ev), stage_keys=list(day["Stages"][0].keys()),
           event_keys=list(ev[0][1].keys()), sample_stage={k: v for k, v in ev[0][0].items() if k != "Events"}, sample_event=ev[0][1], tries={})
gib = [(s, e) for s, e in ev if "Gibraltar" in json.dumps(e)]
out["gibraltar"] = [dict(stage=s.get("Snm"), cnm=s.get("Cnm"), t1=e["T1"][0].get("Nm"), t2=e["T2"][0].get("Nm"), esd=e.get("Esd"), eid=e.get("Eid")) for s, e in gib]
s, e = (gib or ev)[0]
eid = e["Eid"]
for name, u in {
    "scoreboard": f"{B}/scoreboard/soccer/{eid}?locale=en",
    "h2h": f"{B}/h2h/soccer/{eid}?locale=en",
    "h2h2": f"{B}/h2h/soccer/{eid}?locale=en&MD=1",
    "form": f"{B}/form/soccer/{eid}?locale=en",
    "table": f"{B}/table/soccer/{eid}?locale=en",
    "stage": f"{B}/stage/soccer/{s.get('Ccd')}/{s.get('Scd')}/9?locale=en&MD=1",
    "team": f"{B}/team/{e['T1'][0].get('ID')}/0/details?locale=en",
    "incidents": f"{B}/incidents/soccer/{eid}?locale=en",
    "lineups": f"{B}/lineups/soccer/{eid}?locale=en",
    "statistics": f"{B}/statistics/soccer/{eid}?locale=en",
}.items():
    c, t = get(u); out["tries"][name] = dict(url=u, code=c, bytes=len(t), head=t[:1500]); time.sleep(1)
os.makedirs("data/probe", exist_ok=True)
json.dump(out, open("data/probe/livescore.json", "w"), ensure_ascii=False, indent=1)
print({k: (v["code"], v["bytes"]) for k, v in out["tries"].items()})
