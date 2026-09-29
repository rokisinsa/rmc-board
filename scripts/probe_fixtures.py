"""⑤の日程母集団の取りこぼし調査（Portugal U21 vs Gibraltar U21 など）。結果は data/probe/fixtures.json。"""
import gzip, json, os, time, urllib.request
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
     "Accept": "application/json,text/html;q=0.9,*/*;q=0.8", "Accept-Language": "en", "Accept-Encoding": "gzip"}
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=40) as r:
            b = r.read()
            if r.headers.get("Content-Encoding") == "gzip": b = gzip.decompress(b)
            return r.status, b.decode("utf-8", "replace")
    except Exception as e:
        return f"ERR {e}"[:150], ""
out = {}
def probe(name, u, needle=("Gibraltar",)):
    c, t = get(u)
    hits = []
    for n in needle:
        i = t.find(n)
        while i >= 0 and len(hits) < 6:
            hits.append(t[max(0, i - 300): i + 300]); i = t.find(n, i + 1)
    out[name] = dict(url=u, code=c, bytes=len(t), hits=hits, head=t[:400])
    time.sleep(1)
    return t
B = "https://prod-public-api.livescore.com/v1/api/app"
for d in ("20260930", "20261001"):
    probe(f"ls_{d}_jp", f"{B}/date/soccer/{d}/9?countryCode=JP&locale=en&MD=1")
    probe(f"ls_{d}_plain", f"{B}/date/soccer/{d}/9?locale=en")
    probe(f"ls_{d}_gb", f"{B}/date/soccer/{d}/1?countryCode=GB&locale=en&MD=1")
t = probe("ls_stage_u21", f"{B}/stage/soccer/euro-under-21/qualification-group-1/9?locale=en&MD=1", ("Portugal", "Gibraltar"))
for g in range(1, 10):
    probe(f"ls_u21_group{g}", f"{B}/stage/soccer/euro-u21/qualification-group-{g}/9?locale=en&MD=1", ("Portugal", "Gibraltar"))
probe("uefa_u21", "https://match.uefa.com/v5/matches?competitionId=13&fromDate=2026-09-29&toDate=2026-10-02&limit=200&offset=0&order=ASC")
probe("uefa_all", "https://match.uefa.com/v5/matches?fromDate=2026-09-30&toDate=2026-09-30&limit=200&offset=0&order=ASC")
probe("uefa_comps", "https://comp.uefa.com/v2/competitions?limit=200", ("Under-21", "U21"))
probe("fifa_cal", "https://api.fifa.com/api/v3/calendar/matches?from=2026-09-30T00:00:00Z&to=2026-10-01T23:59:59Z&language=en&count=500")
probe("sky_u21", "https://www.skysports.com/football/fixtures", ("Gibraltar", "U21"))
probe("bbc", "https://www.bbc.com/sport/football/scores-fixtures/2026-09-30", ("Gibraltar",))
probe("liquipedia_cs", "https://liquipedia.net/counterstrike/api.php?action=parse&page=Liquipedia:Matches&format=json&prop=text", ("match-info", "team-left"))
probe("vlr_matches", "https://www.vlr.gg/matches", ("match-item",))
probe("hltv_matches", "https://www.hltv.org/matches", ("match-wrapper", "matchTeamName"))
os.makedirs("data/probe", exist_ok=True)
json.dump(out, open("data/probe/fixtures.json", "w"), ensure_ascii=False, indent=1)
print({k: (v["code"], v["bytes"], len(v["hits"])) for k, v in out.items()})
