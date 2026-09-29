"""⑤用のオッズを使わない日程・指標ソースが GitHub Actions から取れるかを確かめる（結果は data/probe/sources.json）。"""
import json, os, time, urllib.request
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
       "Accept": "application/json,text/html;q=0.9,*/*;q=0.8", "Accept-Language": "en"}
D = time.strftime("%Y-%m-%d"); DD = D.replace("-", "")
URLS = {
 "sofascore_football": f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{D}",
 "sofascore_www": f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{D}",
 "espn_soccer_all": f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={DD}",
 "espn_u21q": f"https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.euro_u21_q/scoreboard?dates={DD}",
 "clubelo": f"http://api.clubelo.com/{D}",
 "eloratings_world": "https://www.eloratings.net/World.tsv",
 "eloratings_teams": "https://www.eloratings.net/en.teams.tsv",
 "vrs_repo": "https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/contents/live",
 "tennisexplorer_rank": "https://www.tennisexplorer.com/ranking/atp-men/",
 "tennisabstract_elo": "https://tennisabstract.com/reports/atp_elo_ratings.html",
 "thesportsdb": f"https://www.thesportsdb.com/api/v1/json/3/eventsday.php?d={D}&s=Soccer",
 "liquipedia_cs": "https://liquipedia.net/counterstrike/api.php?action=parse&page=Liquipedia:Matches&format=json&prop=text",
 "fivb": "https://en.volleyballworld.com/volleyball/world-ranking/men",
 "fifa": "https://inside.fifa.com/fifa-world-ranking/men",
 "fotmob": f"https://www.fotmob.com/api/matches?date={DD}",
}
out = {}
for k, u in URLS.items():
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=HDR), timeout=30) as r:
            b = r.read()
            out[k] = dict(code=r.status, bytes=len(b), head=b[:300].decode("utf-8", "replace"))
    except Exception as e:
        out[k] = dict(error=f"{type(e).__name__}: {e}"[:200])
    time.sleep(1)
os.makedirs("data/probe", exist_ok=True)
json.dump(dict(at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), results=out), open("data/probe/sources.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: v.get("code") or v.get("error") for k, v in out.items()}, indent=1))
