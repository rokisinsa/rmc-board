"""⑤ 格差候補発見エンジン用のRating/ランキングを取得して data/ratings/<system>.json に保存する（オッズは使わない）。
GitHub Actions から実行（PCオフで動く）。1つのソースが失敗しても他は続ける。失敗は ok=false と理由を残す。
形式：{"system","sports":[...],"taken_at","ok","source","teams":{"表示名": {"elo":..,"rank":..,...}}}"""
import datetime as dt, gzip, html, json, os, re, sys, time, urllib.request

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ratings")
JST = dt.timezone(dt.timedelta(hours=9))
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
       "Accept-Language": "en", "Accept-Encoding": "gzip"}


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=40) as r:
                b = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    b = gzip.decompress(b)
                return b.decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def txt(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ").strip()


def eloratings():
    teams = {}
    names = {}
    for line in get("https://www.eloratings.net/en.teams.tsv").splitlines():
        c = line.split("\t")
        if len(c) >= 2:
            names[c[0]] = c[1:]
    for line in get("https://www.eloratings.net/World.tsv").splitlines():
        c = line.split("\t")
        if len(c) > 3 and c[3].isdigit():
            for n in names.get(c[2], [c[2]]):
                teams[n] = dict(elo=int(c[3]), rank=int(c[0]))
    return dict(system="eloratings", sports=["サッカー"], source="eloratings.net（代表チームElo）", teams=teams)


def tennis_abstract(tour):
    t = get(f"https://tennisabstract.com/reports/{tour}_elo_ratings.html")
    teams = {}
    for tr in re.findall(r"<tr>(.*?)</tr>", t[t.find('id="reportable"'):], flags=re.S):
        c = [txt(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        if len(c) < 16 or not c[0].isdigit():
            continue
        full = c[1].split()
        if len(full) < 2:
            continue
        key = " ".join(full[1:]) + " " + full[0][0] + "."      # "Sinner J." の形（tennisexplorer・Bovada 表記に合わせる）
        f = lambda v: float(v) if re.match(r"^[\d.]+$", v) else None
        teams[key] = dict(elo=f(c[3]), elo_hard=f(c[6]), elo_clay=f(c[8]), elo_grass=f(c[10]), elo_rank=int(c[0]),
                          rank=int(c[15]) if c[15].isdigit() else None, full_name=c[1])
    return dict(system=f"tennisabstract_{tour}", sports=["テニス"], source=f"Tennis Abstract {tour.upper()} Elo", teams=teams)


def hltv():
    t = get("https://www.hltv.org/ranking/teams")
    teams = {}
    for m in re.finditer(r'<span class="position[^"]*">#(\d+)</span>.*?<span class="name">(.*?)</span><span class="points">\((\d+)', t, flags=re.S):
        teams[txt(m[2])] = dict(rank=int(m[1]), hltv_points=int(m[3]))
    return dict(system="hltv", sports=["CS2"], source="HLTV World Ranking（順位）", teams=teams)


def vrs():
    lst = json.loads(get("https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/contents/live/2026"))
    glob_ = sorted(x["name"] for x in lst if x["name"].startswith("standings_global"))
    md = get(f"https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/live/2026/{glob_[-1]}")
    teams = {}
    for line in md.splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) >= 3 and c[0].isdigit() and re.match(r"^\d+(\.\d+)?$", c[1]):
            teams[c[2]] = dict(rank=int(c[0]), elo=float(c[1]))
    return dict(system="vrs", sports=["CS2"], source=f"Valve Regional Standings（{glob_[-1]}）", teams=teams)


def vlr():
    t = get("https://www.vlr.gg/rankings")
    teams = {}
    for tr in re.findall(r'<tr class="wf-card[^"]*">(.*?)</tr>', t, flags=re.S):
        nm = re.search(r'class="rank-item-team".*?<div>\s*(.*?)\s*<div', tr, flags=re.S)
        rt = re.search(r'class="rank-item-rating[^"]*">\s*<a[^>]*>\s*(\d+)', tr, flags=re.S)
        if nm and rt:
            teams[txt(nm[1])] = dict(elo=int(rt[1]))
    return dict(system="vlr", sports=["VALORANT"], source="VLR.gg Rating", teams=teams)


def world_rugby():
    teams = {}
    for kind in ("mru", "wru"):
        d = json.loads(get(f"https://api.wr-rims-prod.pulselive.com/rugby/v3/rankings/{kind}?language=en"))
        for e in d.get("entries", []):
            nm = e["team"]["name"] + (" Women" if kind == "wru" else "")
            teams[nm] = dict(rating=round(e["pts"], 2), rank=e["pos"])
    return dict(system="world_rugby", sports=["ラグビー"], source="World Rugby Rankings", teams=teams)


SOURCES = [eloratings, lambda: tennis_abstract("atp"), lambda: tennis_abstract("wta"), hltv, vrs, vlr, world_rugby]


def main():
    os.makedirs(OUT, exist_ok=True)
    now = dt.datetime.now(JST).isoformat(timespec="seconds")
    status = {}
    for fn in SOURCES:
        try:
            r = fn()
            r.update(taken_at=now, ok=bool(r["teams"]))
            if not r["teams"]:
                r["error"] = "解析結果が0件（ページ構造の変化の可能性）"
        except Exception as e:
            name = getattr(fn, "__name__", "src")
            r = dict(system=name, ok=False, taken_at=now, error=f"{type(e).__name__}: {e}"[:300], teams={})
        prev = os.path.join(OUT, f"{r['system']}.json")
        if not r["ok"] and os.path.exists(prev):     # 失敗時は前回の正常データを残し、状態だけ記録
            status[r["system"]] = dict(ok=False, error=r.get("error"), kept_previous=True)
        else:
            json.dump(r, open(prev, "w"), ensure_ascii=False, separators=(",", ":"))
            status[r["system"]] = dict(ok=r["ok"], n=len(r["teams"]), error=r.get("error"))
        time.sleep(2)
    json.dump(dict(taken_at=now, sources=status), open(os.path.join(OUT, "status.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(status, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
