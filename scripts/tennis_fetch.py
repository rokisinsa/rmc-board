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
MAX_DETAIL = 400


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
    todo = [m for m in matches if m["list_odds"] and m["start_jst"] > nowj][:MAX_DETAIL]
    fails = 0
    for m in todo:
        try:
            names, books = parse_detail(get(f"{SITE}/match-detail/?id={m['id']}"))
        except Exception:
            fails += 1; continue
        m["names_full"] = names
        m["books"] = books
        pick = next((b for b in PREFER if b in books), next(iter(books), None))
        if pick:
            m["pick"] = dict(book=pick, L=books[pick][0], R=books[pick][1])
        time.sleep(1.0)
    json.dump(dict(taken_at=status["taken_at"], source=status["source"], matches=matches),
              open(os.path.join(OUT, "tennis.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    status.update(ok=True, matches=len(matches), with_list_odds=sum(1 for m in matches if m["list_odds"]),
                  detail_fetched=len(todo) - fails, with_book=sum(1 for m in matches if m.get("pick")),
                  with_bet365=sum(1 for m in matches if "bet365" in (m.get("books") or {})))
    json.dump(status, open(os.path.join(OUT, "tennis_status.json"), "w"), ensure_ascii=False, indent=1)
    print(status); return 0


if __name__ == "__main__":
    sys.exit(main())
