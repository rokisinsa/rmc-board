"""23:45 追加更新（手動実行）：BET CHANNEL本体の実オッズでテニス・バドミントン・スヌーカー・ダーツ・eスポーツ・クリケットを再判定。
元：23:00枠の更新：深掘り結果（/home/claude/dd/*.json）から①〜④を独立判定し、正式採用を台帳へ追記する。"""
import json, os, sys, copy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core
from rmc.build import build

RUN_ID = "run-20260927-2345"
STARTED = "2026-09-27T23:38:00+09:00"
LOCKED = sys.argv[1]            # ロック時刻（実行時の現在時刻）
DD = "/home/claude/dd"
START_SHA = os.popen("git rev-parse HEAD").read().strip()

dd = {x["match_id"]: x for f in ("A_us", "B_soc_bk", "C_ind", "D_es", "E_team")
      for x in json.load(open(f"{DD}/{f}.json", encoding="utf-8"))}
BC_TAKEN = "2026-09-27T23:43:00+09:00"
BC_VIA = "BET CHANNEL LIVEスポーツ prematch配信（sptpub）"
BC = {  # match_id: (L, R, BET CHANNEL event_id, 開始JST)
 "m20260928-959aa524": (1.31, 3.35, "2715908739604553744", "2026-09-28T18:00:00+09:00"),
 "m20260928-59f63a04": (1.14, 4.9, "2715885373766119458", "2026-09-28T16:00:00+09:00"),
 "m20260928-bb2e4540": (1.16, 4.6, "2715908739604553736", "2026-09-28T18:00:00+09:00"),
 "m20260928-7ac3f1df": (4.5, 1.17, "2715908739604553729", "2026-09-28T18:00:00+09:00"),
 "m20260928-ce1cb873": (5.6, 1.11, "2715908739604553731", "2026-09-28T18:00:00+09:00"),
 "m20260928-cdd48d36": (1.07, 6.7, "2715960189823094793", "2026-09-28T09:25:00+09:00"),
 "m20260928-95c4b765": (4.75, 1.15, "2715960189823094819", "2026-09-28T09:55:00+09:00"),
 "m20260928-467991db": (1.15, 4.77, "2715957043075883043", "2026-09-28T10:25:00+09:00"),
 "m20260928-dd27bf6d": (1.27, 3.55, "2715876858204917796", "2026-09-28T15:00:00+09:00"),
 "m20260928-ed8197ff": (1.23, 3.85, "2715876858204917801", "2026-09-28T20:30:00+09:00"),
 "m20260928-5a448cec": (1.07, 7.4, "2715876858204917802", "2026-09-28T20:30:00+09:00"),
 "m20260928-59fc54ca": (1.32, 2.8, "2715960189823094814", "2026-09-28T17:40:00+09:00"),
 "m20260928-b09308b0": (1.26, 3.15, "2715964222356983834", "2026-09-28T19:45:00+09:00"),
 "m20260928-7187d489": (1.45, 2.62, "2715655297296375817", "2026-09-28T02:00:00+09:00"),
 "m20260928-d33b9997": (1.48, 2.48, "2715701825042001954", "2026-09-28T02:00:00+09:00"),
 "m20260928-b744e4f1": (2.02, 1.74, "2715801143950323726", "2026-09-28T02:00:00+09:00"),
 "m20260928-efe86671": (1.14, 5.7, "2715680226892984328", "2026-09-28T09:00:00+09:00"),
 "m20260928-0e4f79c3": (1.10, 7.0, "2715680226892984330", "2026-09-28T13:30:00+09:00"),
}
for mid, (l, r_, eid, st) in BC.items():
    dd[mid]["odds"] = dict(book="BET CHANNEL", via=f"{BC_VIA} event_id={eid}", taken_at=BC_TAKEN, market="MatchWinner",
                           L=l, D=None, R=r_, exact=True, betchannel_event_id=eid)
    dd[mid]["start_jst_confirmed"] = st
matches = core.load("matches.json")
odds = core.load("odds_snapshots.json")
ana_prev = {lg: {r["match_id"]: r for r in core.load(f"analysis/{lg}.json")["rows"]} for lg in core.LOGICS}
ledgers = {lg: core.load(f"ledger/{lg}.json", []) for lg in core.LOGICS}

UA = lambda why: {"unavailable": True, "reason": why}
def val(v, why="取得できず"):
    if v is None or v == "" or (isinstance(v, dict) and v.get("unavailable") and not v.get("reason")):
        return UA(why)
    return v

# ---- 事実の訂正（深掘りで判明） ----
fixes = {}  # 前回適用済み
for mid, (st, note) in fixes.items():
    matches[mid]["start_jst"] = st
    matches[mid]["note"] = (matches[mid].get("note") or "") + "／" + note
    matches[mid]["flags"] = list(set(matches[mid].get("flags", []) + ["開始時刻訂正"]))
extra_flags = {
    "m20260928-388014f0": ["開始時刻要確認"],
    "m20260928-77ecb6ba": ["開始時刻要確認"],
    "m20260928-e74e8709": ["価格が実力差と不整合の可能性"],  # USA 6-0・メキシコに勝利済みなのにメキシコ本命
    "m20260928-0e4f79c3": ["控え中心の編成"], "m20260928-efe86671": ["控え中心の編成"],
    "m20260928-61f41b99": ["主力休養リスク"], "m20260928-b9fea432": ["主力休養リスク"],
}
for mid, fl in extra_flags.items():
    matches[mid]["flags"] = sorted(set(matches[mid].get("flags", []) + fl))
for mid, x in dd.items():
    st = x.get("start_jst_confirmed")
    if isinstance(st, str) and mid not in fixes and st != matches[mid]["start_jst"]:
        matches[mid]["note"] = (matches[mid].get("note") or "") + f"／開始時刻を{st[5:16]}に訂正"
        matches[mid]["start_jst"] = st
    if isinstance(st, str) and mid not in extra_flags and "開始時刻要確認" in matches[mid]["flags"]:
        matches[mid]["flags"].remove("開始時刻要確認")   # 深掘りで開始時刻を確認済み
    if not isinstance(st, str) and "開始時刻要確認" not in matches[mid]["flags"]:
        matches[mid]["flags"].append("開始時刻要確認")

# ---- 深掘りで取った単一ブックのオッズを追記 ----
for mid, x in dd.items():
    o = x.get("odds") or {}
    if o.get("unavailable") or not o.get("L") or mid not in BC:
        continue
    prices = {"L": o["L"], "R": o["R"]}
    if o.get("D"):
        prices = {"L": o["L"], "D": o["D"], "R": o["R"]}
    odds.append(dict(match_id=mid, taken_at=o["taken_at"], source=f'{o["book"]}（{o.get("via","")[:60]}）',
                     market=o.get("market", "ML"), prices=prices, exact=bool(o.get("exact")), book_verified=False))

inventory = sorted([mid for mid, m in matches.items() if m["start_jst"] > LOCKED],
                   key=lambda k: matches[k]["start_jst"])
HARD = {"ショーマッチ", "下位リーグ（整合性リスク）", "価格が実力差と不整合", "価格が実力差と不整合の可能性", "消化試合",
        "主力休養リスク", "親善試合（ローテーション）", "高地開催の可能性", "BO1", "短期戦フォーマット",
        "プレシーズン/カップ戦", "控え中心の編成", "レーバーカップ（消化試合化の可能性）", "開始時刻要確認", "対戦相手未確定"}
STALE = {"m20260928-61f41b99": "numberFireは先発発表前の計算（先発も情報が割れている）",
         "m20260928-64bc9f6f": "numberFireは先発発表前の計算"}
NFL_STALE = "ESPN FPIは2026-08-31更新の開幕前値（第1〜2週とQB欠場を反映していない）"


def exact_odds(mid):
    x = dd.get(mid, {}).get("odds") or {}
    if x.get("unavailable") or not x.get("exact") or not x.get("L"):
        return None
    p = {"L": x["L"], "R": x["R"]}
    if x.get("D"):
        p["D"] = x["D"]
    return p, x


def model(mid):
    mp = dd.get(mid, {}).get("model_prob") or {}
    if not isinstance(mp, dict) or mp.get("unavailable") or mp.get("prob") is None:
        return None
    m = matches[mid]
    if "eloratings" in mp.get("method", ""):
        return dict(usable=False, why="eloratings.netの勝率は引分けを0.5勝として数えるため、1X2の勝率として使えない", **mp)
    if m["sport"] == "アメフト":
        return dict(usable=False, why=NFL_STALE, **mp)
    if mid in STALE:
        return dict(usable=False, why=STALE[mid], **mp)
    p = {mp["side"]: mp["prob"], ("R" if mp["side"] == "L" else "L"): 1 - mp["prob"]}
    return dict(usable=True, p=p, **mp)


def detail(mid, lg, extra):
    x = dd[mid]; m = matches[mid]
    ex = exact_odds(mid)
    d = dict(title=m["sport"], competition=m["competition"], date=m["start_jst"][:10], start_jst=m["start_jst"],
             matchup=f'{m["left"]} vs {m["right"]}', ranking=val(x.get("ranking")), h2h=val(x.get("h2h")),
             recent_form=val(x.get("recent_form")), venue=val(x.get("venue")), lineup=val(x.get("lineup")),
             odds=ex[1] if ex else val(None, "単一ブックの現在オッズを取得できず"),
             odds_exact=bool(ex), external_market=val(None, "複数ブック比較は未実施（公開オッズサイト中心運用）"),
             risks=val(x.get("risks")), missing=val(x.get("missing")), source_urls=x.get("source_urls") or UA("なし"),
             data_as_of=x.get("data_as_of") or STARTED)
    if m["sport"] in ("CS2", "VALORANT", "Dota 2", "LoL", "Rainbow Six"):
        for k in ("format", "lan_online", "roster", "map_pool", "veto", "patch", "series_h2h", "map_h2h", "rating"):
            d[k] = val(x.get(k))
    d.update(extra)
    for k in ("required_prob", "prior_prob", "edge_or_ev", "rationale"):
        d.setdefault(k, UA("オッズ未取得のため算出不可"))
    return d


def entry(lg, mid, side, o, prior, why):
    m = matches[mid]
    return dict(entry_id=f"{lg}-{mid}-{side}", match_id=mid, market=dd[mid]["odds"].get("market", "ML"),
                selection=m["left"] if side == "L" else m["right"], selection_key=side, stake=core.STAKE,
                odds_taken=o, locked_at=LOCKED, odds_source=f'{dd[mid]["odds"]["book"]}（{dd[mid]["odds"]["taken_at"][11:16]}取得）',
                prior_prob=round(prior, 4), rationale=why, result=None)


rows = {lg: [] for lg in core.LOGICS}
new_entries = {lg: [] for lg in core.LOGICS}
for mid in inventory:
    m = matches[mid]
    flags = set(m.get("flags", []))
    hard = sorted(flags & HARD)
    deep = mid in dd and not (isinstance(dd[mid].get("start_jst_confirmed"), str) and dd[mid]["start_jst_confirmed"] < LOCKED)
    ex = exact_odds(mid) if deep else None
    md = model(mid) if deep else None
    for lg in core.LOGICS:
        prev = ana_prev[lg].get(mid)
        if not deep:
            r = copy.deepcopy(prev) if prev else dict(match_id=mid, status="nodata", reason="オッズ未取得", deep_dive=False)
            r["reason"] = r["reason"].replace("一次通過（deep_dive未実施のため正式採用せず）：", "一次通過・深掘り未実施：").replace("一次通過（deep_dive未実施）：", "一次通過・深掘り未実施：")
            r["deep_dive"] = False
            rows[lg].append(r); continue
        # ---------------- 深掘りあり：ロジック別に独立判定 ----------------
        if not ex:
            st = {"r1": "watch", "r2": "watch", "r3": "watch", "r4": "watch"}[lg] if (md and md.get("usable")) or (prev and prev["status"] == "watch") else {"r1": "rejected", "r2": "excluded", "r3": "excluded", "r4": "rejected"}[lg]
            why = {"r1": "深掘り済み。単一ブックの実オッズが取れず正式採用不可（格差判定保留）",
                   "r2": "深掘り済み。実オッズなしで必要勝率を固定できない" + (f"（モデル{md['method'][:20]} {md['p'][md['side']]:.3f}）" if md and md.get('usable') else ""),
                   "r3": "深掘り済み。実オッズなしで市場ベースラインを作れない",
                   "r4": "深掘り済み。実オッズなしでno-vig市場確率を出せない"}[lg]
            rows[lg].append(dict(match_id=mid, status=st, reason=why, deep_dive=True, priced=False,
                                 deep_dive_detail=detail(mid, lg, dict(rationale=why)))); continue
        prices, oraw = ex
        nv, over = core.no_vig(prices)
        sides = [k for k in ("L", "R")]
        name = lambda k: m["left"] if k == "L" else m["right"]
        if lg == "r1":  # 格差・高勝率：実オッズの本命と適正勝率・リスク要因
            k = min(sides, key=lambda s: prices[s]); o = prices[k]; gap = round(nv[k] * 100)
            base = dict(pick=name(k), odds=o, nv=round(nv[k]*100, 1), gap=gap, overround=round(over*100, 1))
            ext = dict(required_prob=round(1/o, 4), prior_prob=round(nv[k], 4), edge_or_ev=f"格差{gap}",
                       rationale=f"①：{name(k)} {o}（{oraw['book']}）。控除後の適正勝率{nv[k]*100:.1f}%。" + (f"リスク：{'・'.join(hard)}" if hard else "重大なリスク要因なし"))
            if o < 1.05: st, why = "rejected", f"リターン過小（{o}）"
            elif o > 1.45: st, why = "rejected", f"格差不足（本命{o}）"
            elif hard: st, why = "watch", "深掘り済み・リスク要因：" + "・".join(hard)
            elif gap >= 70: st, why = "accepted", f"格差{gap}・{oraw['book']} {o}で正式採用"
            elif gap >= 63: st, why = "watch", f"格差{gap}（基準70未満）"
            else: st, why = "rejected", f"格差{gap}"
            r = dict(match_id=mid, status=st, reason=why, deep_dive=True, priced=True, **base)
            if st == "accepted":
                new_entries[lg].append(entry(lg, mid, k, o, nv[k], ext["rationale"]))
        elif lg == "r2":  # 独立モデル勝率レンジ vs 必要勝率
            if not md or not md.get("usable"):
                why = ("独立モデルなし" if not md else f"モデル使用不可：{md['why']}")
                k = min(sides, key=lambda s: prices[s])
                r = dict(match_id=mid, status="excluded", reason=why, deep_dive=True, priced=True, pick=name(k), odds=prices[k], need=round(100/prices[k], 1))
                ext = dict(required_prob=round(1/prices[k], 4), prior_prob=UA(why), edge_or_ev=UA(why), rationale="②：" + why)
            else:
                W = 0.04
                best = max(sides, key=lambda s: md["p"][s]*prices[s])
                o = prices[best]; p = md["p"][best]; lo, hi = p - W, p + W
                evm, evl, evh = p*o-1, lo*o-1, hi*o-1
                r = dict(match_id=mid, deep_dive=True, priced=True, pick=name(best), odds=o, need=round(100/o, 1),
                         est=f"{lo*100:.1f}〜{hi*100:.1f}%", ev_range=f"{evl*100:+.1f}〜{evh*100:+.1f}%")
                ext = dict(required_prob=round(1/o, 4), prior_prob=round(p, 4), edge_or_ev=f"EV{evm*100:+.1f}%",
                           rationale=f"②：{md['method'][:40]}の{name(best)}勝率{p:.3f}を±{W}の幅で評価。必要勝率{1/o:.3f}。")
                risky = [f for f in hard]
                if evl >= 0 and evm >= 0.02 and not risky:
                    r.update(status="formal", reason=f"レンジ下限でもEV{evl*100:+.1f}%")
                    new_entries[lg].append(entry(lg, mid, best, o, p, ext["rationale"]))
                elif evl >= 0 and evm >= 0.02:
                    r.update(status="conditional", reason="EV条件は満たすがリスク要因：" + "・".join(risky))
                elif evh >= 0.02:
                    r.update(status="watch", reason=f"レンジ上側のみプラス（中央EV{evm*100:+.1f}%）")
                else:
                    r.update(status="excluded", reason=f"レンジ全体で必要勝率未満（中央EV{evm*100:+.1f}%）")
        elif lg == "r3":  # 市場差・アップセットリスク（1.50〜3.00）
            cand = [s for s in sides if 1.50 <= prices[s] <= 3.00]
            if not cand:
                k = min(sides, key=lambda s: prices[s])
                r = dict(match_id=mid, status="excluded", reason="対象価格帯（1.50〜3.00）の選択肢なし", deep_dive=True, priced=True, pick=name(k), odds=prices[k])
                ext = dict(required_prob=round(1/prices[k], 4), prior_prob=UA("価格帯外"), edge_or_ev=UA("価格帯外"), rationale="③：価格帯外")
            elif not md or not md.get("usable"):
                k = cand[0]
                why = "独立推定なし（市場との差を測れない）" if not md else f"推定使用不可：{md['why']}"
                r = dict(match_id=mid, status="excluded", reason=why, deep_dive=True, priced=True, pick=name(k), odds=prices[k], need=round(100/prices[k], 1))
                ext = dict(required_prob=round(1/prices[k], 4), prior_prob=UA(why), edge_or_ev=UA(why), rationale="③：" + why)
            else:
                k = max(cand, key=lambda s: md["p"][s] - nv[s]); o = prices[k]
                diff = (md["p"][k] - nv[k]) * 100; ev = md["p"][k]*o - 1
                risk = "中" if o < 1.8 else "中〜高" if o < 2.4 else "高"
                if hard: risk = "高"
                r = dict(match_id=mid, deep_dive=True, priced=True, pick=name(k), odds=o, need=round(100/o, 1),
                         est=f"{md['p'][k]*100:.1f}%", diff=f"{diff:+.1f}pt", upset=risk)
                ext = dict(required_prob=round(1/o, 4), prior_prob=round(md["p"][k], 4), edge_or_ev=f"市場差{diff:+.1f}pt／EV{ev*100:+.1f}%",
                           rationale=f"③：市場ベースライン{nv[k]*100:.1f}%に対し{md['method'][:30]}は{md['p'][k]*100:.1f}%。Upset Risk {risk}。")
                if diff >= 3 and ev >= 0.02 and risk != "高":
                    r.update(status="adopted", reason=f"市場差{diff:+.1f}pt・EV{ev*100:+.1f}%・リスク{risk}")
                    new_entries[lg].append(entry(lg, mid, k, o, md["p"][k], ext["rationale"]))
                elif diff >= 1.5:
                    r.update(status="watch", reason=f"市場差{diff:+.1f}pt・EV{ev*100:+.1f}%・リスク{risk}")
                else:
                    r.update(status="excluded", reason=f"市場差{diff:+.1f}pt")
        else:  # r4 PRO EDGE：no-vig市場50%＋独立ベース50%＋専門補正0
            if not md or not md.get("usable"):
                k = min(sides, key=lambda s: prices[s])
                why = "独立ベース確率なし" if not md else f"ベース確率使用不可：{md['why']}"
                r = dict(match_id=mid, status="rejected", reason=why + "（市場確率の流用は禁止）", deep_dive=True, priced=True,
                         pick=name(k), odds=prices[k], fair=round(nv[k]*100, 1), reliability="low")
                ext = dict(required_prob=round(1/prices[k], 4), prior_prob=UA(why), edge_or_ev=UA(why), rationale="④：" + why)
            else:
                fin = {s: 0.5*nv[s] + 0.5*md["p"][s] for s in sides}
                k = max(sides, key=lambda s: fin[s]*prices[s]); o = prices[k]
                edge = (fin[k] - nv[k]) * 100; ev = fin[k]*o - 1
                rel = "high" if oraw["book"] in ("DraftKings", "FanDuel", "bet365", "Pinnacle", "BET CHANNEL") else "medium"
                if hard: rel = "low"
                r = dict(match_id=mid, deep_dive=True, priced=True, pick=name(k), odds=o, fair=round(nv[k]*100, 1),
                         final=round(fin[k]*100, 1), edge=f"{edge:+.1f}pt", ev=f"{ev*100:+.1f}%",
                         min_odds=__import__("math").ceil(100/fin[k])/100,
                         reliability=rel, base_prob=round(md["p"][k], 4), market_prob=round(nv[k], 4))
                ext = dict(required_prob=round(1/o, 4), prior_prob=round(fin[k], 4), edge_or_ev=f"EDGE{edge:+.1f}pt／EV{ev*100:+.1f}%",
                           rationale=f"④：market {nv[k]:.3f}（no-vig）＋base {md['p'][k]:.3f}（{md['method'][:25]}）を等分、expert_adjustment 0 → final {fin[k]:.3f}。")
                if edge >= 3 and ev >= 0.03 and rel != "low":
                    r.update(status="accepted", reason=f"EDGE{edge:+.1f}pt・EV{ev*100:+.1f}%")
                    new_entries[lg].append(entry(lg, mid, k, o, fin[k], ext["rationale"]))
                elif edge >= 1.5 and ev > -0.01:
                    r.update(status="watch", reason=f"EDGE{edge:+.1f}pt・EV{ev*100:+.1f}%（基準EV+3%未達）")
                else:
                    r.update(status="rejected", reason=f"EDGE{edge:+.1f}pt・EV{ev*100:+.1f}%")
        r["rationale"] = ext["rationale"]
        r["deep_dive_detail"] = detail(mid, lg, ext)
        rows[lg].append(r)

# ---- 保存 ----
core.save("matches.json", matches)
core.save("odds_snapshots.json", odds)
os.makedirs(core.path("snapshots", RUN_ID), exist_ok=True)
for lg in core.LOGICS:
    a = dict(logic=lg, run_id=RUN_ID, run_started_at=STARTED, decided_at=LOCKED, rows=rows[lg])
    core.save(f"analysis/{lg}.json", a)
    core.save(f"snapshots/{RUN_ID}/{lg}.json", a)
    have = {e["entry_id"] for e in ledgers[lg]}
    new_entries[lg] = [e for e in new_entries[lg] if e["entry_id"] not in have]
    core.save(f"ledger/{lg}.json", ledgers[lg] + new_entries[lg])

FORMAL = core.FORMAL
coverage = {}
for mid in inventory:
    sp = matches[mid]["sport"]
    c = coverage.setdefault(sp, dict(event_count=0, priced_upcoming_count=0, market_count=0))
    c["event_count"] += 1
    if any(o["match_id"] == mid for o in odds):
        c["priced_upcoming_count"] += 1; c["market_count"] += 1
for lg in core.LOGICS:
    for r in rows[lg]:
        sp = matches[r["match_id"]]["sport"]
        lc = coverage[sp].setdefault(lg, dict(screened=0, deep_dive=0, formal=0, watch=0, rejected=0, nodata=0))
        lc["screened"] += 1; lc["deep_dive"] += int(bool(r.get("deep_dive")))
        s = r["status"]
        lc["formal" if s == FORMAL[lg] else "watch" if s in ("watch", "conditional") else "nodata" if s == "nodata" else "rejected"] += 1
for sp, c in coverage.items():
    for lg in core.LOGICS:
        lc = c[lg]
        if c["priced_upcoming_count"] and not lc["deep_dive"]:
            lc["deep_dive_waiver"] = "未実施：本回の深掘り枠に入らず（次回の対象）"
runs = core.load("automation-runs.json")
prev = runs[-1]
gone = {sp: "対象時間内に未開始の試合なし（全試合開始済み）" for sp in prev["coverage"] if sp not in coverage}
CL = {f"{i:02d}": False for i in range(1, 42)}
notes = {}
for k in ("01", "07", "08", "09", "10", "13", "16", "20", "28", "29", "30", "31", "32", "33"):
    CL[k] = True
notes.update({"02": "BET CHANNEL全メニュー未取得（公開オッズサイト中心運用）", "03": "カジ旅・遊雅堂はログイン必要で確認不能、bet365は一部のみ",
              "04": "走査は21:45取得分の再利用。9/28 20:40〜22:30開始の試合は未走査", "05": "eスポーツはCS2/Dota2/LoL/R6/VALORANTのみ",
              "11": "競技別ショートリストは①基準の順位のみ", "12": "水球など一部競技で深掘り未実施", "14": "H2H・直近成績が取れていない項目あり（unavailable記録）",
              "15": "map pool/veto等が未取得の試合あり", "17": "既存カードなし（初回）", "21": "精算対象なし", "27": "敗戦カードなし",
              "34": "push後に確認", "35": "push後に確認", "36": "push後に確認", "37": "push後に確認", "38": "push後に確認", "39": "push後に確認"})
run = dict(run_id=RUN_ID, slot="23:00（追加）", started_at=STARTED, finished_at=core.now_jst(), start_sha=START_SHA,
           status="partial", previous_run_ok=False, carried_blockers=prev.get("blockers", []),
           inventory_match_ids=inventory, coverage=coverage, sports_disappeared=gone,
           sources=dict(betchannel="取得：LIVEスポーツのprematch配信（24時間以内 896件、うちシミュレーション系175件を除く実競技721件）とスポーツベット本体のmatchlist（77件）。深掘り対象18試合はBET CHANNELの実オッズで判定",
                        kajitabi="確認不能：ログインが必要", bet365="一部取得：ドランメン戦のみbet365の実オッズ", yuugado="確認不能：ログインが必要"),
           betchannel_inventory=dict(taken_at=BC_TAKEN, total_24h=896, simulated=175, real=721, sportsbook_main=77,
                                     real_by_sport={"サッカー": 265, "テニス": 113, "バスケットボール": 88, "アイス・ホッケー": 47, "バレーボール": 23, "野球": 19,
                                                    "ハンドボール": 16, "アメリカン・フットボール": 15, "ダーツ": 15, "リーグ・オブ・レジェンド": 15, "フロアボール": 13,
                                                    "カウンターストライク": 12, "クリケット": 11, "バドミントン": 10, "スヌーカー": 8, "フットサル": 8, "Fortnite": 6,
                                                    "パデルテニス": 6, "レインボーシックス": 5, "水球": 5, "バスケットボール3x3": 4, "ワールド・オブ・タンクス": 4,
                                                    "Dota 2": 2, "Mobile Legends": 2, "Nascar": 2, "ゴルフ": 2, "卓球": 2, "ラグビーユニオンフットボール": 1,
                                                    "ラグビーリーグ": 1, "StarCraft: Brood War": 1}),
           blockers=["BET CHANNELのインベントリ（721件）は取得したが、RMCの走査対象（318件）への取り込みと全件判定は次回（項目2・4〜6）",
                     "カジ旅・遊雅堂は確認不能（項目3）",
                     "BET CHANNELの配信はPCの内蔵ブラウザ経由でしか取得できない（クラウドから直接は接続不可）",
                     "複数ブックのクロスチェック未実施（項目3・8）"],
           checklist=CL, checklist_notes=notes)
runs.append(run)
core.save("automation-runs.json", runs)
build()
for lg in core.LOGICS:
    print(lg, [(e["selection"], e["odds_taken"]) for e in new_entries[lg]])
print("inventory", len(inventory))
