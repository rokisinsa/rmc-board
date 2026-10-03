"""tennisexplorer の結果一覧（/results/）から直近数日のテニスの試合結果を取得して data/basic/tennis_results.json に保存する。
GitHub Actions（odds-fetch の tennis_fetch.py の最後）から実行。クラウドの更新セッションからは tennisexplorer に接続できないため、
未精算カードの結果確認（第三優先：専門結果DB）に使う。キーは match-detail の id（= odds_feed/tennis.json の id・matches の feed_ids "te:<id>"）。
閲覧・分析用（結果の取得のみ）。"""
import datetime as dt, html, json, os, re, sys, time, urllib.request
from zoneinfo import ZoneInfo

HDR = {"User-Agent": "Mozilla/5.0 (compatible; rmc-board-fetch/1.0)", "Accept-Language": "en"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://www.tennisexplorer.com"
CET = ZoneInfo("Europe/Prague")
JST = dt.timezone(dt.timedelta(hours=9))
DAYS = int(os.environ.get("TENNIS_RESULT_DAYS", "5"))


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
    s = re.sub(r"<sup>(.*?)</sup>", r"(\1)", s, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ").strip()


def parse_results(page, day):
    out, tour = [], None
    cur = None
    for tr in re.findall(r"<tr[^>]*>.*?</tr>", page, flags=re.S):
        if 'class="head flags"' in tr:
            m = re.search(r'<td class="t-name"[^>]*>(.*?)</td>', tr, flags=re.S)
            tour = txt(m[1]) if m else None
            continue
        m = re.search(r'<tr id="[a-z]*(\d+)(b?)"', tr)
        if not m:
            continue
        name = re.search(r'<td class="t-name"[^>]*>(.*?)</td>', tr, flags=re.S)
        name = txt(name[1]) if name else None
        res = re.search(r'<td class="result"[^>]*>(.*?)</td>', tr, flags=re.S)
        res = txt(res[1]) if res else ""
        scores = [txt(c) for c in re.findall(r'<td class="score"[^>]*>(.*?)</td>', tr, flags=re.S)]
        note = txt(tr)
        if not m[2]:
            tm = re.search(r'class="first time"[^>]*>\s*(\d{1,2}:\d{2})', tr)
            mid = re.search(r"/match-detail/\?id=(\d+)", tr)
            if not mid:
                cur = None; continue
            st = None
            if tm:
                h, mi = map(int, tm[1].split(":"))
                st = dt.datetime(day.year, day.month, day.day, h, mi, tzinfo=CET).astimezone(JST).isoformat(timespec="seconds")
            cur = dict(id=mid[1], tournament=tour, start_jst=st, date_cet=day.isoformat(), p1=name, p2=None,
                       sets=[res, None], games=[scores, None], retired=bool(re.search(r"\bret\.?|retired|w/o|walkover|def\.", note, re.I)),
                       raw1=note[:200])
            out.append(cur)
        elif cur is not None and cur.get("p2") is None:
            cur["p2"] = name; cur["sets"][1] = res; cur["games"][1] = scores; cur["raw2"] = note[:200]
            cur["retired"] = cur["retired"] or bool(re.search(r"\bret\.?|retired|w/o|walkover|def\.", note, re.I))
    for c in out:
        a, b = c["sets"]
        c["final"] = bool(re.fullmatch(r"\d+", a or "") and re.fullmatch(r"\d+", b or "") and int(a) != int(b))
        if c["final"]:
            c["winner"] = "p1" if int(a) > int(b) else "p2"
    return out


def main():
    now = dt.datetime.now(CET)
    res, errs = {}, []
    for back in range(DAYS):
        d = (now - dt.timedelta(days=back)).date()
        try:
            page = get(f"{SITE}/results/?type=all&year={d.year}&month={d.month:02d}&day={d.day:02d}")
            for r in parse_results(page, d):
                res[r["id"]] = r
        except Exception as e:
            errs.append(f"{d}: {type(e).__name__}: {e}"[:200])
        time.sleep(2)
    bdir = os.path.join(ROOT, "data", "basic")
    os.makedirs(bdir, exist_ok=True)
    json.dump(dict(taken_at=dt.datetime.now(JST).isoformat(timespec="seconds"),
                   source=f"tennisexplorer 結果一覧（/results/・直近{DAYS}日・CET日付）", errors=errs, results=res),
              open(os.path.join(bdir, "tennis_results.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    print("tennis_results", len(res), "final", sum(1 for r in res.values() if r["final"]), errs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
