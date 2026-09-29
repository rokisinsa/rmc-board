"""パーサを書くための生HTML/JSONのサンプルを保存（data/probe/raw/）。"""
import gzip, json, os, re, time, urllib.request
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
     "Accept-Language": "en", "Accept-Encoding": "gzip"}
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=40) as r:
            b = r.read()
            if r.headers.get("Content-Encoding") == "gzip": b = gzip.decompress(b)
            return b.decode("utf-8", "replace")
    except Exception as e:
        return f"ERROR {e}"
os.makedirs("data/probe/raw", exist_ok=True)
def save(name, txt, lim=250000):
    open(f"data/probe/raw/{name}", "w").write(txt[:lim]); time.sleep(1.5)
D = time.strftime("%Y%m%d", time.gmtime(time.time() + 9 * 3600))
# テニス：一覧→最初の試合の選手ページ・H2H
lst = get(f"https://www.tennisexplorer.com/matches/?type=all&year={D[:4]}&month={D[4:6]}&day={D[6:]}")
i = lst.find('match-detail'); save("te_list.html", lst[max(0, i - 20000):i + 30000])
mid = re.search(r"/match-detail/\?id=(\d+)", lst)
if mid:
    md = get(f"https://www.tennisexplorer.com/match-detail/?id={mid[1]}")
    j = md.find('id="center"'); save("te_detail.html", md[j:j + 120000])
    ps = re.findall(r'href="(/player/[^"]+/)"', md)
    if ps:
        pg = get("https://www.tennisexplorer.com" + ps[0]); k = pg.find('id="center"'); save("te_player.html", pg[k:k + 150000])
save("te_rank.html", get("https://www.tennisexplorer.com/ranking/atp-men/")[:200000])
save("ta_atp_elo.html", get("https://tennisabstract.com/reports/atp_elo_ratings.html"), 80000)
save("hltv_rank.html", get("https://www.hltv.org/ranking/teams"), 300000)
save("vlr_rank.html", get("https://www.vlr.gg/rankings"), 150000)
save("golgg.html", get("https://gol.gg/teams/list/season-S16/split-ALL/tournament-ALL/"), 200000)
save("pdc_oom.html", get("https://www.pdc.tv/order-of-merit/pdc-order-merit"), 400000)
save("world_rugby.json", get("https://api.wr-rims-prod.pulselive.com/rugby/v3/rankings/mru?language=en"))
save("vrs_live.json", get("https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/contents/live/2026"))
st = get(f"https://prod-public-api.livescore.com/v1/api/app/stage/soccer/uefa-nations-league/league-a-group-3/9?locale=en&MD=1")
save("ls_stage.json", st, 60000)
save("ls_hockey_day.json", get(f"https://prod-public-api.livescore.com/v1/api/app/date/hockey/{D}/9?countryCode=JP&locale=en&MD=1"), 60000)
save("liquipedia_dota.json", get("https://liquipedia.net/dota2/api.php?action=parse&page=Liquipedia:Upcoming_and_ongoing_matches&format=json&prop=text"), 200000)
save("mlb.json", get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={D[:4]}-{D[4:6]}-{D[6:]}&hydrate=probablePitcher(stats(group=[pitching],type=[season]))"), 100000)
print("done")
