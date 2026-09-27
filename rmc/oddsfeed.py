"""data/odds_feed/bovada.json（GitHub Actions が保存した公開オッズ）を matches.json の試合に対応づける。"""
import json, os, re
from . import core


def _n(s):
    s = re.sub(r"\(.*?\)|esports?|gaming|team|club|fc|academy|\.|-", " ", str(s or "").lower())
    return {t for t in s.split() if len(t) > 1}


def load():
    p = core.path("odds_feed", "bovada.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def match(feed, m, hours=3):
    """試合 m（matches.json の1行）に対応する配信イベントを返す: (event, prices{L,R[,D]}) or (None, None)。
    開始時刻が±hours以内で、左右それぞれのチーム名トークンが配信の2チームと重なるものだけ採用（向きも判定）。"""
    t0 = core.parse(m["start_jst"]).timestamp()
    L, R = _n(m["left"]), _n(m["right"])
    for ev in (feed or {}).get("events") or []:
        mk = ev.get("market")
        if not mk or abs(core.parse(ev["start_jst"]).timestamp() - t0) > hours * 3600:
            continue
        oc = mk["outcomes"]
        two = [o for o in oc if (o.get("type") or "") != "D" and (o.get("name") or "").lower() != "draw"]
        if len(two) != 2:
            continue
        a, b = _n(two[0]["name"]), _n(two[1]["name"])
        if L & a and R & b:
            pl, pr = two[0]["dec"], two[1]["dec"]
        elif L & b and R & a:
            pl, pr = two[1]["dec"], two[0]["dec"]
        else:
            continue
        pr_ = {"L": pl, "R": pr}
        d = [o for o in oc if o not in two]
        if d:
            pr_["D"] = d[0]["dec"]
        return ev, pr_
    return None, None
