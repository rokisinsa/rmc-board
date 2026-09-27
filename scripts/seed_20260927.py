"""初期データ投入（1回限り）：2026-09-27 21:45 JST の走査結果（387件・一次判定のみ）を新データ構造に変換する。
deep_dive は未実施なので正式採用は0件。一次判定の「採用」は watch（一次通過）として記録する。"""
import hashlib, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc.core import save, LOGICS, no_vig
from rmc.build import build

SRC = sys.argv[1]
d = json.load(open(SRC, encoding="utf-8"))
SCAN = d["scan_at"]
RUN_ID = "run-20260927-2145-seed"

SPORT_NORM = {"アメフト": "アメフト", "野球": "野球", "サッカー": "サッカー", "テニス": "テニス", "CS2": "CS2",
              "VALORANT": "VALORANT", "Dota 2": "Dota 2", "LoL": "LoL", "Rainbow Six": "Rainbow Six"}
MAP = {
    "r1": {"採用": ("watch", "一次通過（deep_dive未実施のため正式採用せず）："), "監視": ("watch", ""), "除外": ("rejected", ""), "データ不足": ("nodata", "")},
    "r2": {"採用": ("watch", "一次通過（deep_dive未実施）："), "監視": ("watch", ""), "除外": ("excluded", ""), "データ不足": ("nodata", "")},
    "r3": {"採用": ("watch", "一次通過（deep_dive未実施）："), "監視": ("watch", ""), "除外": ("excluded", ""), "データ不足": ("nodata", "")},
    "r4": {"採用": ("watch", "一次通過（deep_dive未実施）："), "監視": ("watch", ""), "除外": ("rejected", ""), "データ不足": ("nodata", "")},
}
KEEP = {"r1": ("pick", "odds", "nv", "gap", "conf", "overround", "three_way", "adj_reason"),
        "r2": ("pick", "odds", "need", "est", "ev_range", "adj_reason"),
        "r3": ("pick", "odds", "need", "est", "diff", "upset", "adj_reason"),
        "r4": ("pick", "odds", "fair", "final", "edge", "ev", "min_odds", "reliability", "adj_reason")}

sys.path.insert(0, os.path.dirname(SRC))
from events import E  # 元の走査データ（オッズ・左右）

matches, odds, ids = {}, [], []
for i, ev in enumerate(E):
    r1 = d["logics"]["r1"]["rows"][i]
    key = "|".join([ev["sport"], ev["comp"], ev["start"], ev["left"], ev["right"]])
    mid = "m" + r1["start"][:10].replace("-", "") + "-" + hashlib.sha1(key.encode()).hexdigest()[:8]
    ids.append(mid)
    matches[mid] = dict(sport=ev["sport"], competition=ev["comp"], round=None, start_jst=r1["start"],
                        left=ev["left"], right=ev["right"], home_away="left=home（NFL/MLBはleft=away）",
                        status="scheduled", result=None, note=ev["note"], flags=ev["flags"])
    if ev["odds"]:
        o = ev["odds"]
        prices = {"L": o[0], "R": o[1]} if len(o) == 2 else {"L": o[0], "D": o[1], "R": o[2]}
        odds.append(dict(match_id=mid, taken_at=SCAN, source=ev["src"], market="1X2" if len(o) == 3 else "ML",
                         prices=prices, exact=not any(s in ev["src"] for s in ("平均", "最高値")),
                         book_verified=False))
assert len(ids) == len(set(ids))
save("matches.json", matches)
save("odds_snapshots.json", odds)

coverage = {}
for lg in LOGICS:
    rows = []
    for i, r in enumerate(d["logics"][lg]["rows"]):
        st, pre = MAP[lg][r["status"]]
        row = dict(match_id=ids[i], status=st, reason=pre + r["reason"], deep_dive=False,
                   priced=bool(E[i]["odds"]))
        row.update({k: r[k] for k in KEEP[lg] if k in r})
        rows.append(row)
        sp = E[i]["sport"]
        c = coverage.setdefault(sp, dict(event_count=0, priced_upcoming_count=0, market_count=0))
        lc = c.setdefault(lg, dict(screened=0, deep_dive=0, formal=0, watch=0, rejected=0, nodata=0))
        lc["screened"] += 1
        key = {"watch": "watch", "nodata": "nodata"}.get(st, "rejected")
        lc[key] += 1
    save(f"analysis/{lg}.json", dict(logic=lg, run_id=RUN_ID, run_started_at="2026-09-27T20:21:00+09:00", rows=rows))
for i, ev in enumerate(E):
    c = coverage[ev["sport"]]
    c["event_count"] += 1
    if ev["odds"] and ev["start"] >= "09-27 21:45":
        c["priced_upcoming_count"] += 1
        c["market_count"] += 1

for lg in LOGICS + ("experience",):
    save(f"ledger/{lg}.json", [])

run = dict(
    run_id=RUN_ID, slot="adhoc", started_at="2026-09-27T20:21:00+09:00", finished_at=SCAN,
    start_sha="(初回・リポジトリ作成前)", status="partial", previous_run_ok=None,
    inventory_match_ids=ids, coverage=coverage,
    sources=dict(betchannel="確認不能：ページがJavaScript描画でクラウドから取得不可（公開オッズサイト中心で運用）",
                 kajitabi="未確認：ログイン必要", bet365="一部：メディア掲載のbet365値（FOX Sports 9/25）", yuugado="未確認：ログイン必要"),
    blockers=["deep_dive 未実施（全競技・全ロジック）→ 正式採用0件",
              "BET CHANNEL インベントリ未取得（event_id なし）",
              "既存RMCカードの結果再確認は未実施（旧サイトのデータ未移行）",
              "GitHub未接続のため commit/Actions/Pages 未実施"],
    checklist={},
)
save("automation-runs.json", [run])
build()
print(len(matches), "matches", len(odds), "odds")
