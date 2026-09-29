"""⑤ 格差候補発見エンジンの日程母集団を複数経路で補完する（オッズは使わない）。GitHub Actions から実行（PCオフで動く）。
総合日程（LiveScore）に無い大会・試合を、競技団体・大会公式・主要データサイトの日程から足すため。
- サッカー：UEFA 公式 match API（全UEFA大会：A代表・U21・U19・女子・クラブ大会）、FIFA 公式 calendar API
- eスポーツ：Liquipedia（CS2・Dota 2・LoL・VALORANT・R6・MLBB・Honor of Kings）、VLR.gg（VALORANT）
結果：data/basic/fixtures_extra.json（{taken_at, sources:{名前:{ok,n,error}}, fixtures:[{sport,source,competition,start_jst,t1,t2}]}）"""
import datetime as dt, gzip, html, json, os, re, sys, time, urllib.request

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "basic")
JST = dt.timezone(dt.timedelta(hours=9))
UA = "rmc-board-fixtures/1.0 (https://github.com/rokisinsa/rmc-board; schedule only)"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
       "Accept": "application/json,text/html;q=0.9,*/*;q=0.8", "Accept-Language": "en", "Accept-Encoding": "gzip"}
DAYS = 3   # 今日・明日・明後日（JST）。⑤の走査窓（48時間）を確実に覆う


def get(url, headers=None, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers or HDR), timeout=40) as r:
                b = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    b = gzip.decompress(b)
                return b.decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def txt(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).replace("\xa0", " ").strip()


def to_jst(iso_utc):
    t = dt.datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.astimezone(JST).isoformat(timespec="seconds")


AGE = {"U21": " U21", "U19": " U19", "U17": " U17", "U20": " U20", "U23": " U23"}


def uefa_name(t):
    n = t.get("internationalName") or (t.get("translations") or {}).get("displayName", {}).get("EN") or t.get("displayName")
    det = str(t.get("teamTypeDetail") or "")
    for k, v in AGE.items():
        if k in det and n and k not in n:
            n += v
    if "WOMEN" in det and n and "Women" not in n:
        n += " Women"
    return n


def uefa(today):
    out = []
    frm, to = today.isoformat(), (today + dt.timedelta(days=DAYS)).isoformat()
    off = 0
    while True:
        x = json.loads(get(f"https://match.uefa.com/v5/matches?fromDate={frm}&toDate={to}&limit=100&offset={off}&order=ASC"))
        if not x:
            break
        if off == 0:
            os.makedirs(os.path.join(os.path.dirname(OUT), "probe", "raw"), exist_ok=True)
            json.dump(x[:2], open(os.path.join(os.path.dirname(OUT), "probe", "raw", "uefa_match.json"), "w"), ensure_ascii=False, indent=1)
        for m in x:
            ko = (m.get("kickOffTime") or {}).get("dateTime") or m.get("kickOffTime")
            if not ko or not m.get("homeTeam") or not m.get("awayTeam"):
                continue
            comp = ((m.get("competition") or {}).get("metaData") or {}).get("name") or (m.get("competition") or {}).get("code")
            rnd = ((m.get("round") or {}).get("metaData") or {}).get("name") or ""
            grp = ((m.get("group") or {}).get("metaData") or {}).get("groupName") or ""
            out.append(dict(sport="サッカー", source="UEFA公式", competition=" / ".join(x for x in (comp, rnd, grp) if x),
                            start_jst=to_jst(ko), t1=uefa_name(m["homeTeam"]), t2=uefa_name(m["awayTeam"]),
                            status=m.get("status"), ext_id=f"uefa:{m.get('id')}"))
        if len(x) < 100:
            break
        off += 100
        time.sleep(1)
    return out


def fifa(today):
    frm = dt.datetime.combine(today, dt.time()).isoformat() + "Z"
    to = dt.datetime.combine(today + dt.timedelta(days=DAYS), dt.time()).isoformat() + "Z"
    x = json.loads(get(f"https://api.fifa.com/api/v3/calendar/matches?from={frm}&to={to}&language=en&count=500"))
    out = []
    for m in x.get("Results") or []:
        h, a = m.get("Home") or {}, m.get("Away") or {}
        nm = lambda t: ((t.get("TeamName") or [{}])[0]).get("Description")
        if not nm(h) or not nm(a) or not m.get("Date"):
            continue
        comp = ((m.get("CompetitionName") or [{}])[0]).get("Description")
        out.append(dict(sport="サッカー", source="FIFA公式", competition=comp, start_jst=to_jst(m["Date"]), t1=nm(h), t2=nm(a),
                        ext_id=f"fifa:{m.get('IdMatch')}"))
    return out


LQ = {"counterstrike": "CS2", "dota2": "Dota 2", "leagueoflegends": "LoL", "valorant": "VALORANT", "rainbowsix": "Rainbow Six",
      "mobilelegends": "Mobile Legends", "honorofkings": "King of Glory"}


def liquipedia(today):
    out, errs = [], {}
    end = dt.datetime.combine(today + dt.timedelta(days=DAYS), dt.time(), tzinfo=JST).timestamp()
    for wiki, sport in LQ.items():
        try:
            x = json.loads(get(f"https://liquipedia.net/{wiki}/api.php?action=parse&page=Liquipedia:Matches&format=json&prop=text",
                               headers=dict(HDR, **{"User-Agent": UA})))
            page = x["parse"]["text"]["*"]
        except Exception as e:
            errs[wiki] = f"{type(e).__name__}: {e}"[:150]
            time.sleep(31); continue
        for blk in re.split(r'<div class="match-info">', page)[1:]:
            ts = re.search(r'data-timestamp="(\d+)"', blk)
            names = re.findall(r'<span class="name"[^>]*>(?:<a[^>]*title="([^"]+)"[^>]*>)?([^<]*)', blk)
            teams = [html.unescape(a or b).strip() for a, b in names if (a or b).strip()]
            teams = [re.sub(r"\s*\(page does not exist\)$", "", t) for t in teams if t.upper() != "TBD"]
            comp = re.search(r'class="match-info-tournament-name"[^>]*>.*?<a[^>]*title="([^"]+)"', blk, flags=re.S)
            if not ts or len(teams) < 2 or int(ts[1]) > end:
                continue
            st = dt.datetime.fromtimestamp(int(ts[1]), JST).isoformat(timespec="seconds")
            out.append(dict(sport=sport, source="Liquipedia", competition=html.unescape(comp[1]) if comp else None,
                            start_jst=st, t1=teams[0], t2=teams[1]))
        time.sleep(31)   # Liquipedia API の利用規約（parse は30秒に1回）
    return out, errs


def vlr(today):
    t = get("https://www.vlr.gg/matches")
    out = []
    date = None
    for part in re.split(r'(<div class="wf-label mod-large">)', t):
        m = re.match(r"\s*([A-Za-z]{3}, [A-Za-z]+ \d{1,2}, \d{4})", txt(part[:200]))
        if m:
            date = dt.datetime.strptime(m[1], "%a, %B %d, %Y").date()
        for it in re.findall(r'<a href="/\d+/[^"]+" class="wf-module-item match-item[^"]*">(.*?)</a>', part, flags=re.S):
            tm = re.search(r'match-item-time">\s*([\d:]+ [AP]M)', it)
            names = [txt(x) for x in re.findall(r'class="match-item-vs-team-name">(.*?)</div>\s*</div>', it, flags=re.S)]
            ev = re.search(r'class="match-item-event[^"]*">(.*?)</div>', it, flags=re.S)
            if not (date and tm and len(names) >= 2):
                continue
            clock = dt.datetime.strptime(tm[1], "%I:%M %p").time()
            # vlr.gg は既定でUTC表示（アクセス元のタイムゾーン指定なし）
            st = dt.datetime.combine(date, clock, tzinfo=dt.timezone.utc).astimezone(JST)
            out.append(dict(sport="VALORANT", source="VLR.gg", competition=re.sub(r"\s+", " ", txt(ev[1])) if ev else None,
                            start_jst=st.isoformat(timespec="seconds"), t1=names[0].split("\n")[0].strip(), t2=names[1].split("\n")[0].strip()))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    now = dt.datetime.now(JST)
    today = now.date()
    fixtures, status = [], {}
    for name, fn in (("UEFA公式", uefa), ("FIFA公式", fifa), ("VLR.gg", vlr)):
        try:
            r = fn(today)
            fixtures += r
            status[name] = dict(ok=True, n=len(r))
        except Exception as e:
            status[name] = dict(ok=False, n=0, error=f"{type(e).__name__}: {e}"[:300])
        time.sleep(2)
    try:
        r, errs = liquipedia(today)
        fixtures += r
        status["Liquipedia"] = dict(ok=len(errs) < len(LQ), n=len(r), errors=errs or None)
    except Exception as e:
        status["Liquipedia"] = dict(ok=False, n=0, error=f"{type(e).__name__}: {e}"[:300])
    json.dump(dict(taken_at=now.isoformat(timespec="seconds"), source="公式・主要データサイトの日程（オッズは含まない）",
                   sources=status, fixtures=fixtures), open(os.path.join(OUT, "fixtures_extra.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(status, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
