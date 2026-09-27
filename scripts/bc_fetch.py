"""BET CHANNEL（LIVEスポーツ prematch配信 sptpub）を直接取得して data/bc/feed/ に保存する。GitHub Actions / VPS から実行する。
閲覧・分析用。48時間以内の試合について、勝敗系の市場（186/219/11/1/406）だけを残す。"""
import datetime as dt, json, os, sys, time, urllib.request

BASE = "https://api-h-c7818b61-608.sptpub.com/api/v4/prematch/brand/2564963746585911298/ja/"
HDR = {"User-Agent": "Mozilla/5.0 (compatible; rmc-board-fetch/1.0)", "Origin": "https://bet-channel.com",
       "Referer": "https://bet-channel.com/", "Accept": "application/json"}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bc", "feed")
JST = dt.timezone(dt.timedelta(hours=9))
KEEP = ("186", "219", "11", "1", "406")


def get(path):
    req = urllib.request.Request(BASE + str(path), headers=HDR)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    os.makedirs(OUT, exist_ok=True)
    now = dt.datetime.now(JST)
    status = dict(taken_at=now.isoformat(timespec="seconds"), runner=os.environ.get("RUNNER_NAME") or os.uname().nodename)
    try:
        idx = get(0)
        B = {k: dict(idx.get(k) or {}) for k in ("events", "tournaments", "categories", "sports")}
        for v in (idx.get("top_events_versions") or []) + (idx.get("rest_events_versions") or []):
            p = get(v)
            for k in B:
                B[k].update(p.get(k) or {})
            time.sleep(0.3)
    except Exception as e:  # 取得できなかった理由を残す
        status.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
        json.dump(status, open(os.path.join(OUT, "status.json"), "w"), ensure_ascii=False, indent=1)
        print(status); return 1
    lim = now.timestamp() + 48 * 3600
    ev = {}
    for eid, e in B["events"].items():
        d = e.get("desc") or {}
        if not d.get("scheduled") or d["scheduled"] < now.timestamp() or d["scheduled"] > lim:
            continue
        ev[eid] = dict(s=d.get("sport"), t=d.get("tournament"), c=d.get("category"), at=d["scheduled"], type=d.get("type"),
                       teams=[x.get("name") for x in d.get("competitors") or []],
                       m={k: v for k, v in (e.get("markets") or {}).items() if k in KEEP})
    used_t = {x["t"] for x in ev.values()}
    feed = dict(taken_at=status["taken_at"], events=ev,
                sports={k: (v.get("name") if isinstance(v, dict) else v) for k, v in B["sports"].items()},
                tournaments={k: (v.get("name") if isinstance(v, dict) else v) for k, v in B["tournaments"].items() if k in used_t})
    json.dump(feed, open(os.path.join(OUT, "latest.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    status.update(ok=True, events_total=len(B["events"]), events_48h=len(ev))
    json.dump(status, open(os.path.join(OUT, "status.json"), "w"), ensure_ascii=False, indent=1)
    print(status); return 0


if __name__ == "__main__":
    sys.exit(main())
