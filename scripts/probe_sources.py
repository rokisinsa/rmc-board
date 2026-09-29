"""⑤用のオッズを使わない日程・指標ソースが GitHub Actions から取れるかを確かめる（結果は data/probe/sources.json）。"""
import json, os, time, urllib.request
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
       "Accept": "application/json,text/html;q=0.9,*/*;q=0.8", "Accept-Language": "en"}
D = time.strftime("%Y-%m-%d"); DD = D.replace("-", "")
URLS = {
 "livescore_soccer": f"https://prod-public-api.livescore.com/v1/api/app/date/soccer/{DD}/9?countryCode=JP&locale=en&MD=1",
 "livescore_tennis": f"https://prod-public-api.livescore.com/v1/api/app/date/tennis/{DD}/9?countryCode=JP&locale=en&MD=1",
 "livescore_hockey": f"https://prod-public-api.livescore.com/v1/api/app/date/hockey/{DD}/9?countryCode=JP&locale=en&MD=1",
 "livescore_basketball": f"https://prod-public-api.livescore.com/v1/api/app/date/basketball/{DD}/9?countryCode=JP&locale=en&MD=1",
 "livescore_cricket": f"https://prod-public-api.livescore.com/v1/api/app/date/cricket/{DD}/9?countryCode=JP&locale=en&MD=1",
 "clubelo": f"http://api.clubelo.com/{D}",
 "clubelo_https": f"https://api.clubelo.com/{D}",
 "tennisabstract_wta_elo": "https://tennisabstract.com/reports/wta_elo_ratings.html",
 "soccerway": "https://int.soccerway.com/matches/",
 "worldfootball": "https://www.worldfootball.net/matches_today/",
 "vlr": "https://www.vlr.gg/matches",
 "vlr_rank": "https://www.vlr.gg/rankings",
 "golgg": "https://gol.gg/teams/list/season-S16/split-ALL/tournament-ALL/",
 "hltv_rank": "https://www.hltv.org/ranking/teams",
 "pdc_oom": "https://www.pdc.tv/order-of-merit/pdc-order-merit",
 "snooker_org": "https://api.snooker.org/?t=10&st=p&s=2026",
 "espn_scoreboard_nhl": f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates={DD}",
 "cricbuzz": "https://www.cricbuzz.com/cricket-schedule/upcoming-series/international",
 "icc_rank": "https://www.icc-cricket.com/rankings/team-rankings/mens/odi",
 "bwf": "https://bwfbadminton.com/rankings/",
 "world_rugby": "https://api.wr-rims-prod.pulselive.com/rugby/v3/rankings/mru?language=en",
 "mlb_statsapi": f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={D}&hydrate=probablePitcher",
 "nhl_api": "https://api-web.nhle.com/v1/standings/now",
 "fbref": "https://fbref.com/en/matches/",
}

out = {}
for k, u in URLS.items():
    try:
        h = dict(HDR); h["Accept-Encoding"] = "gzip"
        with urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=30) as r:
            b = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                import gzip; b = gzip.decompress(b)
            out[k] = dict(code=r.status, bytes=len(b), head=b[:300].decode("utf-8", "replace"))
    except Exception as e:
        out[k] = dict(error=f"{type(e).__name__}: {e}"[:200])
    time.sleep(1)
os.makedirs("data/probe", exist_ok=True)
json.dump(dict(at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), results=out), open("data/probe/sources2.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: v.get("code") or v.get("error") for k, v in out.items()}, indent=1))
