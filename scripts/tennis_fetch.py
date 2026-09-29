"""tennisexplorer から今日・明日のテニスの試合と、各試合のブック別オッズ（bet365・Pinnacle など）を取得して
data/odds_feed/tennis.json に保存する。GitHub Actions から実行（PCオフで動く）。閲覧・分析用。
一覧の時刻は中央ヨーロッパ時間（Europe/Prague）表示なので JST に直して保存する。"""
import datetime as dt, html, json, os, re, sys, time, urllib.request
from zoneinfo import ZoneInfo

HDR = {"User-Agent": "Mozilla/5.0 (compatible; rmc-board-fetch/1.0)", "Accept-Language": "en"}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "odds_feed")
SITE = "https://www.tennisexplorer.com"
CET = ZoneInfo("Europe/Prague")
JST = dt.timezone(dt.timedelta(hours=9))
PREFER = ("bet365", "Pinnacle", "1xBet", "Betsson", "bwin", "Unibet", "William Hill", "BetVictor")
MAX_DETAIL = 900


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(10 * (i + 1))


def txt(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ").strip()


def parse_list(page, day):
    out, tour = [], None
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", page, flags=re.S):
        if 'class="head flags"' in tr:
            m = re.search(r'<td class="t-name"[^>]*>(.*?)</td>', tr, flags=re.S)
            tour = txt(m[1]) if m else None
            continue
        m = re.search(r'<tr id="r(\d+)(b?)"', tr)
        if not m:
            continue
        name = re.search(r'<td class="t-name">(.*?)</td>', tr, flags=re.S)
        name = txt(name[1]) if name else None
        if not m[2]:
            tm = re.search(r'class="first time"[^>]*>\s*(\d{1,2}:\d{2})', tr)
            odds = re.findall(r'<td class="course"[^>]*>([\d.]+)</td>', tr)
            mid = re.search(r"/match-detail/\?id=(\d+)", tr)
            if not (tm and mid):
                cur = None; continue
            h, mi = map(int, tm[1].split(":"))
            st = dt.datetime(day.year, day.month, day.day, h, mi, tzinfo=CET).astimezone(JST)
            cur = dict(id=mid[1], tournament=tour, start_jst=st.isoformat(timespec="seconds"), p1=name, p2=None,
                       list_odds=[float(x) for x in odds] if len(odds) == 2 else None)
            out.append(cur)
        elif out and out[-1].get("p2") is None:
            out[-1]["p2"] = name
    return out


def parse_detail(page):
    i = page.find('id="oddsMenu-1-data"')
    if i < 0:
        return None, {}
    j = page.find('id="oddsMenu-2-data"', i)
    tb = page[i:j if j > 0 else i + 200000]
    head = re.search(r'<td class="k1">(.*?)</td>\s*<td class="k2">(.*?)</td>', tb, flags=re.S)
    names = (txt(head[1]), txt(head[2])) if head else None
    books = {}
    for row in re.split(r'<tr class="(?:one|two)">', tb)[1:]:
        b = re.search(r'<span class="t">(.*?)</span>', row)
        k1 = re.search(r'<td class="k1"><div class="odds-in[^"]*">([\d.]+)', row)
        k2 = re.search(r'<td class="k2"><div class="odds-in[^"]*">([\d.]+)', row)
        if b and k1 and k2:
            books[txt(b[1])] = [float(k1[1]), float(k2[1])]
    return names, books


def _cells(tr):
    return [txt(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)]


def parse_basic(page):
    """⑤ 格差候補発見用の基本指標（オッズ以外）：両者のランキング・今季サーフェス別勝敗・H2H・直近の試合。
    オッズの表（oddsMenu）は読まない。"""
    out = {}
    hd = re.search(r'<span class="upper">([\d.]+)</span>,\s*([\d:]+),\s*<a[^>]*>(.*?)</a>,\s*([^,<]*),\s*([^,<]*)<', page)
    if hd:
        out.update(date=hd[1], tournament=txt(hd[3]), surface=txt(hd[4]) or None)
    rk = re.search(r'<td class="tr">([^<]*)</td>\s*<th>Singles ranking</th>\s*<td class="tl">([^<]*)</td>', page)
    if rk:
        num = lambda v: int(re.sub(r"\D", "", v)) if re.search(r"\d", v) else None
        out["rank"] = [num(rk[1]), num(rk[2])]
    i = page.find('id="balMenu-1-data"')
    if i > 0:
        wl = {}
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page[i:page.find("</table>", i)], flags=re.S):
            c = _cells(tr)
            if len(c) == 3 and c[0] not in ("Surface",):
                wl[c[0]] = [c[1], c[2]]
        out["surface_wl_2026"] = wl
    i = page.find("Head-to-head:")
    if i > 0:
        tb = page[i:page.find("</table>", i)]
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tb, flags=re.S)[1:]
        h2h = []
        for a, b in zip(rows[0::2], rows[1::2]):
            ca, cb = _cells(a), _cells(b)
            try:
                year = ca[0]; ta, sa = ca[2], int(ca[3]); tb_, sb = cb[0], int(cb[1])
            except (IndexError, ValueError):
                continue
            games = [(x, y) for x, y in zip(ca[5:10], cb[2:7]) if x.strip().isdigit() and y.strip().isdigit()]
            h2h.append(dict(year=year, event=ca[1], first=ta, second=tb_, sets=[sa, sb], games=[f"{x}-{y}" for x, y in games]))
        out["h2h"] = h2h
    i = page.find("Latest matches")
    lat = []
    if i > 0:
        for m in re.finditer(r'<table class="result mutual"', page[i:]):
            seg = page[i + m.start(): page.find("</table>", i + m.start())]
            rows, comp, date = [], None, None
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", seg, flags=re.S):
                if "icon-result" not in tr:
                    hh = re.search(r'<a[^>]*>(.*?)</a>.*?(\d{2}\.\d{2}\.\d{4})', tr, flags=re.S)
                    if hh:
                        comp, date = txt(hh[1]), hh[2]
                    continue
                res = "W" if "icon-result win" in tr else "L" if "icon-result lose" in tr else None
                names = re.findall(r'<a href="/player/[^"]+/"[^>]*>(.*?)</a>', tr)
                me = re.search(r"<strong>(.*?)</strong>", tr)
                sc = re.search(r'title="([^"]*)">(\d+):(\d+)<', tr)
                if not (res and sc and len(names) == 2 and me):
                    continue
                opp = [txt(n) for n in names if "<strong>" not in n]
                a, b = int(sc[2]), int(sc[3])
                rows.append(dict(date=date, comp=comp, opp=opp[0] if opp else None, res=res,
                                 units_won=a if res == "W" else b, units_lost=b if res == "W" else a, detail=sc[1]))
            lat.append(rows)
            if len(lat) == 2:
                break
    out["latest"] = lat
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    now = dt.datetime.now(CET)
    status = dict(taken_at=dt.datetime.now(JST).isoformat(timespec="seconds"), source="tennisexplorer（ブック別オッズ）")
    try:
        matches = []
        for add in (0, 1):
            d = (now + dt.timedelta(days=add)).date()
            matches += parse_list(get(f"{SITE}/matches/?type=all&year={d.year}&month={d.month:02d}&day={d.day:02d}"), d)
            time.sleep(2)
    except Exception as e:
        status.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
        json.dump(status, open(os.path.join(OUT, "tennis_status.json"), "w"), ensure_ascii=False, indent=1)
        print(status); return 1
    nowj = dt.datetime.now(JST).isoformat()
    # オッズの有無に関係なく全試合の詳細を取る（⑤ 格差候補発見はオッズのない試合も対象）
    todo = [m for m in matches if m["start_jst"] > nowj and m.get("p2")][:MAX_DETAIL]
    basic = {}
    fails = 0

    def one(m):
        page = get(f"{SITE}/match-detail/?id={m['id']}")
        time.sleep(0.3)
        return m, page

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:      # 4並列（1本あたり0.3秒休止）で所要時間を短くする
        futs = [ex.submit(one, m) for m in todo]
        for fu in futs:
            try:
                m, page = fu.result()
            except Exception:
                fails += 1; continue
            names, books = parse_detail(page)
            try:
                basic[m["id"]] = dict(parse_basic(page), p1=m["p1"], p2=m["p2"], start_jst=m["start_jst"], tournament_list=m["tournament"])
            except Exception as e:
                basic[m["id"]] = dict(error=f"{type(e).__name__}: {e}"[:200], p1=m["p1"], p2=m["p2"], start_jst=m["start_jst"])
            m["names_full"] = names
            m["books"] = books
            pick = next((b for b in PREFER if b in books), next(iter(books), None))
            if pick:
                m["pick"] = dict(book=pick, L=books[pick][0], R=books[pick][1])
    bdir = os.path.join(os.path.dirname(OUT), "basic")
    os.makedirs(bdir, exist_ok=True)
    json.dump(dict(taken_at=status["taken_at"], source="tennisexplorer 試合詳細（ランキング・H2H・直近・サーフェス別勝敗。オッズは含まない）",
                   matches=basic), open(os.path.join(bdir, "tennis.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(dict(taken_at=status["taken_at"], source=status["source"], matches=matches),
              open(os.path.join(OUT, "tennis.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    status.update(ok=True, matches=len(matches), with_list_odds=sum(1 for m in matches if m["list_odds"]),
                  detail_fetched=len(todo) - fails, with_book=sum(1 for m in matches if m.get("pick")),
                  with_bet365=sum(1 for m in matches if "bet365" in (m.get("books") or {})))
    json.dump(status, open(os.path.join(OUT, "tennis_status.json"), "w"), ensure_ascii=False, indent=1)
    print(status); return 0


if __name__ == "__main__":
    sys.exit(main())
