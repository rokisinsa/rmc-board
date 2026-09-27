"""公開オッズ配信（Bovada の公開 coupon JSON）を取得して data/odds_feed/ に保存する。GitHub Actions から実行（PCオフで動く）。
閲覧・分析用。各試合の勝敗系市場（Moneyline / 3-Way / Match Winner 等）の実オッズ（decimal）を残す。"""
import datetime as dt, json, os, sys, time, urllib.error, urllib.request

BASE = "https://www.bovada.lv/services/sports/event/coupon/events/A/description/"
Q = "?marketFilterId=def&preMatchOnly=true&lang=en"
PATHS = ["esports", "tennis", "darts", "snooker", "badminton", "table-tennis", "volleyball", "handball", "soccer", "basketball",
         "baseball", "football", "hockey", "cricket", "rugby-union", "rugby-league", "aussie-rules", "ufc-mma", "boxing", "water-polo",
         "futsal"]
HDR = {"User-Agent": "Mozilla/5.0 (compatible; rmc-board-fetch/1.0)", "Accept": "application/json"}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "odds_feed")
JST = dt.timezone(dt.timedelta(hours=9))
WIN = ("moneyline", "match winner", "winner", "3-way", "match result", "to win", "fight winner", "match odds")


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1:
                raise
            time.sleep(30 * (i + 1))


def pick_market(ev):
    for dg in ev.get("displayGroups") or []:
        for m in dg.get("markets") or []:
            d = (m.get("description") or "").lower()
            per = m.get("period") or {}
            if not per.get("main", True) and "match" not in (per.get("description") or "").lower():
                continue
            if any(w in d for w in WIN) and 2 <= len(m.get("outcomes") or []) <= 3 and "spread" not in d and "total" not in d:
                oc = [dict(name=o.get("description"), type=o.get("type"), dec=float(o["price"]["decimal"]), am=o["price"].get("american"))
                      for o in m["outcomes"] if (o.get("price") or {}).get("decimal")]
                if len(oc) == len(m["outcomes"]):
                    return dict(market=m.get("description"), period=per.get("description"), outcomes=oc)
    return None


def main():
    os.makedirs(OUT, exist_ok=True)
    now = dt.datetime.now(JST)
    status = dict(taken_at=now.isoformat(timespec="seconds"), source="Bovada 公開coupon JSON", paths={})
    events = []
    for p in PATHS:
        try:
            data = get(BASE + p + Q)
            if not data:          # 空応答は一時的なことがあるので1回だけ取り直す
                time.sleep(20); data = get(BASE + p + Q)
        except Exception as e:
            status["paths"][p] = f"失敗 {type(e).__name__}: {e}"[:160]; continue
        n = 0
        for grp in data or []:
            league = " / ".join(x.get("description", "") for x in (grp.get("path") or [])[::-1][1:]) or p
            for ev in grp.get("events") or []:
                st = ev.get("startTime")
                if not st or st / 1000 > now.timestamp() + 72 * 3600:
                    continue
                mk = pick_market(ev)
                events.append(dict(id=ev.get("id"), sport=p, league=league, desc=ev.get("description"),
                                   start_jst=dt.datetime.fromtimestamp(st / 1000, JST).isoformat(timespec="seconds"),
                                   teams=[dict(name=c.get("name"), home=c.get("home")) for c in ev.get("competitors") or []],
                                   live=ev.get("live"), market=mk, link=ev.get("link")))
                n += 1
        status["paths"][p] = f"取得 {n}件"
        time.sleep(4)
    status.update(ok=bool(events), events=len(events), priced=sum(1 for e in events if e["market"]))
    json.dump(dict(taken_at=status["taken_at"], source=status["source"], events=events),
              open(os.path.join(OUT, "bovada.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(status, open(os.path.join(OUT, "status.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(status, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
