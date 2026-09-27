"""23:00枠の定時更新（run-20260927-2300b）：競技別サブエージェントの走査・深掘り結果（SCRATCH/dd/*.json）から
①〜④を独立判定し、正式採用を台帳へ追記する。方式は scripts/run_20260927_2300.py と同じ。"""
import json, os, sys, copy, glob, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core
from rmc.build import build

RUN_ID = "run-20260927-2300b"
STARTED = "2026-09-27T22:56:05+09:00"
LOCKED = sys.argv[1]            # ロック時刻（実行時の現在時刻）
DD = sys.argv[2]                # サブエージェント出力ディレクトリ
START_SHA = sys.argv[3]
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00$")

groups = {os.path.basename(f)[:-5]: json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(f"{DD}/*.json"))}
dd = {x["match_id"]: x for g in groups.values() for x in g.get("deep_dives", [])}
matches = core.load("matches.json")
odds = core.load("odds_snapshots.json")
ana_prev = {lg: {r["match_id"]: r for r in core.load(f"analysis/{lg}.json")["rows"]} for lg in core.LOGICS}
prev_run_id = core.load("analysis/r1.json")["run_id"]
ledgers = {lg: core.load(f"ledger/{lg}.json", []) for lg in core.LOGICS}
ledger_ids = {lg: {e["entry_id"] for e in ledgers[lg]} for lg in core.LOGICS}

UA = lambda why: {"unavailable": True, "reason": why}
def val(v, why="取得できず"):
    if v is None or v == "" or v == [] or (isinstance(v, dict) and v.get("unavailable") and not v.get("reason")):
        return UA(why)
    if isinstance(v, list):
        return "／".join(map(str, v))
    return v

# ---- 新規試合（走査で判明した取りこぼし） ----
for g in groups.values():
    for x in g.get("new_events", []):
        mid = x["match_id"]
        if mid in matches:
            continue
        matches[mid] = dict(sport=x["sport"], competition=x["competition"], round=None, start_jst=x["start_jst"],
                            left=x["left"], right=x["right"], home_away=x.get("home_away") or "left=home",
                            status="scheduled", result=None, note=f"{RUN_ID}の走査で追加", flags=["新規追加"])
        o = x.get("odds") or {}
        if not o.get("unavailable") and o.get("L") and o.get("R") and ISO.match(o.get("taken_at", "")):
            pr = {"L": o["L"], "R": o["R"]} if not o.get("D") else {"L": o["L"], "D": o["D"], "R": o["R"]}
            odds.append(dict(match_id=mid, taken_at=o["taken_at"], source=f'{o["book"]}（{o.get("via","")[:60]}）',
                             market=o.get("market", "ML"), prices=pr, exact=bool(o.get("exact")), book_verified=False))

# ---- 開始時刻の訂正・状態変更 ----
for g in groups.values():
    for c in g.get("changes", []):
        m = matches.get(c["match_id"])
        if not m:
            continue
        if c.get("start_jst_new") and c["start_jst_new"] != m["start_jst"]:
            m["note"] = (m.get("note") or "") + f"／開始時刻を{m['start_jst'][5:16]}→{c['start_jst_new'][5:16]}に訂正（{c.get('source','')[:80]}）"
            m["start_jst"] = c["start_jst_new"]
        if c.get("status") in ("cancelled", "postponed"):
            m["status"] = c["status"]; m["note"] = (m.get("note") or "") + "／" + c.get("note", "")
        if "要再確認" in c.get("note", "") or "可能性" in c.get("note", ""):
            m["flags"] = sorted(set(m.get("flags", []) + ["開始時刻要確認"]))
        elif "開始時刻要確認" in m.get("flags", []):
            m["flags"].remove("開始時刻要確認")

for mid, x in dd.items():
    fl = [f.split("（")[0] for f in (x.get("extra_flags") or [])]
    if fl:
        matches[mid]["flags"] = sorted(set(matches[mid].get("flags", []) + fl))
    st = x.get("start_jst_confirmed")
    if isinstance(st, str) and st != matches[mid]["start_jst"]:
        matches[mid]["note"] = (matches[mid].get("note") or "") + f"／開始時刻を{st[5:16]}に訂正"
        matches[mid]["start_jst"] = st
    if not isinstance(st, str) and "開始時刻要確認" not in matches[mid]["flags"]:
        matches[mid]["flags"].append("開始時刻要確認")

# ---- 深掘りで取った単一ブックのオッズを追記（取得時刻不明の記事値は exact=false） ----
def odds_ok(o):
    return bool(o) and not o.get("unavailable") and o.get("L") and o.get("R")
for mid, x in dd.items():
    o = x.get("odds") or {}
    if not odds_ok(o):
        continue
    prices = {"L": o["L"], "R": o["R"]} if not o.get("D") else {"L": o["L"], "D": o["D"], "R": o["R"]}
    timed = bool(ISO.match(str(o.get("taken_at", ""))))
    src = f'{o["book"]}（{str(o.get("via",""))[:60]}）' + ("" if timed else f'［掲載時刻不明：{str(o.get("taken_at"))[:30]}］')
    odds.append(dict(match_id=mid, taken_at=o["taken_at"] if timed else x["data_as_of"], source=src,
                     market=o.get("market", "ML"), prices=prices, exact=bool(o.get("exact")) and timed, book_verified=False))

inventory = sorted([mid for mid, m in matches.items() if m["start_jst"] > LOCKED and m["status"] == "scheduled"
                    and m["start_jst"] <= "2026-09-28T23:10:00+09:00"],
                   key=lambda k: matches[k]["start_jst"])

HARD = {"ショーマッチ", "下位リーグ（整合性リスク）", "価格が実力差と不整合", "価格が実力差と不整合の可能性", "消化試合",
        "主力休養リスク", "親善試合（ローテーション）", "高地開催の可能性", "BO1", "短期戦フォーマット",
        "プレシーズン/カップ戦", "控え中心の編成", "レーバーカップ（消化試合化の可能性）", "開始時刻要確認", "対戦相手未確定", "データ不足"}
STALE = {"m20260928-61f41b99": "numberFireは先発発表前の計算（先発も情報が割れている）",
         "m20260928-64bc9f6f": "numberFireは先発発表前の計算",
         "m20260928-2540a13c": "SportsGrid自社モデルは手法・先発反映時刻が不明（開示のある公開モデルではない）"}
NFL_STALE = "ESPN FPIは2026-08-31更新の開幕前値（第1〜2週とQB欠場を反映していない）"


def exact_odds(mid):
    x = dd.get(mid, {}).get("odds") or {}
    if x.get("unavailable") or not x.get("exact") or not x.get("L") or not x.get("R") or not ISO.match(str(x.get("taken_at", ""))):
        return None   # 単一ブック・取得時刻が確定した現在値だけを正式採用に使う
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
    if m["sport"] == "アメフト" and "FPI" in mp.get("method", ""):
        return dict(usable=False, why=NFL_STALE, **mp)
    if not isinstance(mp.get("prob"), (int, float)):
        return None
    if mid in STALE:
        return dict(usable=False, why=STALE[mid], **mp)
    p = {mp["side"]: mp["prob"], ("R" if mp["side"] == "L" else "L"): 1 - mp["prob"]}
    return dict(usable=True, p=p, **mp)


def detail(mid, lg, extra):
    x = dd[mid]; m = matches[mid]
    ex = exact_odds(mid)
    d = dict(title=m["sport"], competition=m["competition"], date=m["start_jst"][:10], start_jst=m["start_jst"],
             matchup=f'{m["left"]} vs {m["right"]}', ranking=val(x.get("ranking"), "取得できず"), h2h=val(x.get("h2h")),
             recent_form=val(x.get("recent_form")), venue=val(x.get("venue")), lineup=val(x.get("lineup")),
             odds=ex[1] if ex else (dict(x["odds"], note="取得時刻不明・非単一ブック等のため正式採用には使わない") if odds_ok(x.get("odds")) else val(x.get("odds") if isinstance(x.get("odds"), dict) and x["odds"].get("reason") else None, "単一ブックの現在オッズを取得できず")),
             odds_exact=bool(ex), external_market=val(None, "複数ブック比較は未実施（公開オッズサイト中心運用）"),
             risks=val(x.get("risks")), missing=val(x.get("missing")), source_urls=x.get("source_urls") or UA("なし"),
             data_as_of=x.get("data_as_of") or STARTED)
    if m["sport"] in __import__("rmc.validate").validate.ESPORTS:
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
                odds_taken=o, locked_at=LOCKED, odds_source=f'{dd[mid]["odds"]["book"]}（{dd[mid]["odds"]["taken_at"][11:16]}取得・{str(dd[mid]["odds"].get("via",""))[:60]}）',
                prior_prob=round(prior, 4), rationale=why, result=None)


rows = {lg: [] for lg in core.LOGICS}
new_entries = {lg: [] for lg in core.LOGICS}
def add_entry(lg, e):
    if e["entry_id"] in ledger_ids[lg]:
        return   # 同じ試合・同じ選択は既に正式採用済み（台帳は append-only・重複禁止）
    new_entries[lg].append(e)
for mid in inventory:
    m = matches[mid]
    flags = set(m.get("flags", []))
    hard = sorted(flags & HARD)
    deep = mid in dd
    ex = exact_odds(mid) if deep else None
    md = model(mid) if deep else None
    for lg in core.LOGICS:
        prev = ana_prev[lg].get(mid)
        if not deep:
            if prev and prev.get("deep_dive"):
                r = copy.deepcopy(prev)   # 前回深掘りの判定（ロック済みの事前分析）を継続
                r["carried_from"] = prev_run_id
                if not r["reason"].startswith("前回深掘り"):
                    r["reason"] = f"前回深掘り（{prev_run_id}）の判定を継続：" + r["reason"]
            else:
                r = copy.deepcopy(prev) if prev else dict(match_id=mid, status="nodata", reason="本回の走査で追加・単一ブックのオッズ未取得", deep_dive=False, priced=False)
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
                add_entry(lg, entry(lg, mid, k, o, nv[k], ext["rationale"]))
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
                    add_entry(lg, entry(lg, mid, best, o, p, ext["rationale"]))
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
                    add_entry(lg, entry(lg, mid, k, o, md["p"][k], ext["rationale"]))
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
                rel = "high" if oraw["book"] in ("DraftKings", "FanDuel", "bet365", "Pinnacle") else "medium"
                if hard: rel = "low"
                r = dict(match_id=mid, deep_dive=True, priced=True, pick=name(k), odds=o, fair=round(nv[k]*100, 1),
                         final=round(fin[k]*100, 1), edge=f"{edge:+.1f}pt", ev=f"{ev*100:+.1f}%",
                         min_odds=__import__("math").ceil(100/fin[k])/100,
                         reliability=rel, base_prob=round(md["p"][k], 4), market_prob=round(nv[k], 4))
                ext = dict(required_prob=round(1/o, 4), prior_prob=round(fin[k], 4), edge_or_ev=f"EDGE{edge:+.1f}pt／EV{ev*100:+.1f}%",
                           rationale=f"④：market {nv[k]:.3f}（no-vig）＋base {md['p'][k]:.3f}（{md['method'][:25]}）を等分、expert_adjustment 0 → final {fin[k]:.3f}。")
                if edge >= 3 and ev >= 0.03 and rel != "low":
                    r.update(status="accepted", reason=f"EDGE{edge:+.1f}pt・EV{ev*100:+.1f}%")
                    add_entry(lg, entry(lg, mid, k, o, fin[k], ext["rationale"]))
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
    core.save(f"ledger/{lg}.json", ledgers[lg] + new_entries[lg])
core.save(f"snapshots/{RUN_ID}/inventory.json", inventory)

FORMAL = core.FORMAL
odds_mids = {o["match_id"] for o in odds}
coverage = {}
for mid in inventory:
    sp = matches[mid]["sport"]
    c = coverage.setdefault(sp, dict(event_count=0, priced_upcoming_count=0, market_count=0))
    c["event_count"] += 1
    if mid in odds_mids:
        c["priced_upcoming_count"] += 1; c["market_count"] += 1
for lg in core.LOGICS:
    for r in rows[lg]:
        sp = matches[r["match_id"]]["sport"]
        lc = coverage[sp].setdefault(lg, dict(screened=0, deep_dive=0, deep_dive_carried=0, formal=0, watch=0, rejected=0, nodata=0))
        lc["screened"] += 1
        if r.get("deep_dive"):
            lc["deep_dive_carried" if r.get("carried_from") else "deep_dive"] += 1
        s = r["status"]
        lc["formal" if s == FORMAL[lg] else "watch" if s in ("watch", "conditional") else "nodata" if s == "nodata" else "rejected"] += 1
scan_notes = {sp: v for g in groups.values() for sp, v in (g.get("scan") or {}).items()}
for sp, c in coverage.items():
    for lg in core.LOGICS:
        lc = c[lg]
        if c["priced_upcoming_count"] and not lc["deep_dive"]:
            lc["deep_dive_waiver"] = ("本回の新規深掘りなし（前回深掘り分を継続判定）" if lc["deep_dive_carried"] else
                                      "本回の深掘り枠に入らず：サブエージェントが時間内に単一ブック値・試合ページを取得できなかった（次回の対象）")
runs = core.load("automation-runs.json")
prev = runs[-1]
gone = {sp: "対象時間内に未開始の試合なし（全試合開始済み）" for sp in prev["coverage"] if sp not in coverage}
json.dump(dict(coverage=coverage, gone=gone, scan=scan_notes, new={lg: [(e["entry_id"], e["selection"], e["odds_taken"]) for e in new_entries[lg]] for lg in core.LOGICS}),
          open(os.path.join(DD, "..", "run_out.json"), "w"), ensure_ascii=False, indent=1)
for lg in core.LOGICS:
    print(lg, [(e["selection"], e["odds_taken"]) for e in new_entries[lg]])
print("inventory", len(inventory))
