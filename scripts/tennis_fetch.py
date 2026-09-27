"""tennisexplorer から今日・明日のテニスの試合と、各試合のブック別オッズ（bet365 など）を取得して data/odds_feed/tennis.json に保存する。
GitHub Actions から実行（PCオフで動く）。閲覧・分析用。"""
import datetime as dt, html, json, os, re, sys, time, urllib.request

HDR = {"User-Agent": "Mozilla/5.0 (compatible; rmc-board-fetch/1.0)", "Accept-Language": "en"}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "odds_feed")
JST = dt.timezone(dt.timedelta(hours=9))


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def main():
    os.makedirs(OUT, exist_ok=True)
    if "--sample" in sys.argv:
      try:
        d = dt.datetime.now(JST)
        lst = get(f"https://www.tennisexplorer.com/matches/?type=all&year={d.year}&month={d.month:02d}&day={d.day:02d}")
        open(os.path.join(OUT, "_sample_list.html"), "w").write(lst)
        ids = re.findall(r"/match-detail/\?id=(\d+)", lst)
        if ids:
            open(os.path.join(OUT, "_sample_detail.html"), "w").write(get(f"https://www.tennisexplorer.com/match-detail/?id={ids[0]}"))
        print("sample saved", len(lst), len(ids)); return 0
      except Exception as e:
        json.dump(dict(error=f"{type(e).__name__}: {e}"[:300]), open(os.path.join(OUT, "_sample_status.json"), "w"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
