"""23:20 追加更新（手動実行）：eスポーツの再取得と72時間以内全試合の徹底判定。
BET CHANNEL prematch配信（data/bc/20260928-2156-esports.txt・実チーム系140件）でオッズを更新し、
追加で徹底調査した23試合（/home/claude/dd/es2 → data/facts 反映済み）と既存の facts を合わせ、①〜④を全件独立判定する。
使い方: python scripts/run_20260928_2320_esports.py <ロック時刻JST>"""
import copy, glob, json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core, bcfeed, bcmap, model
from rmc.build import build

RUN_ID = "run-20260928-2320"
STARTED = "2026-09-28T21:57:00+09:00"
LOCKED = sys.argv[1]
START_SHA = os.popen("git rev-parse HEAD").read().strip()
BC_FILE = "data/bc/20260928-2156-esports.txt"
DD = "/home/claude/dd/full2"
BC_VIA = "BET CHANNEL LIVEスポーツ prematch配信（sptpub）"

taken, events = bcfeed.load(os.path.join(core.ROOT, BC_FILE))
matches = core.load("matches.json")
odds = core.load("odds_snapshots.json")
ana_prev = {lg: {r["match_id"]: r for r in core.load(f"analysis/{lg}.json")["rows"]} for lg in core.LOGICS}
ledgers = {lg: core.load(f"ledger/{lg}.json", []) for lg in core.LOGICS}
dd = {}  # 徹底取得済みの事実：data/facts にあるものすべて（今回のes2追補分は反映済み）
def _load_facts(mid):
    p = core.path("facts", f"{mid}.json")
    if os.path.exists(p):
        x = json.load(open(p, encoding="utf-8"))
        if (x.get("left") or {}).get("form") or (x.get("right") or {}).get("form") or x.get("unavailable"):
            dd[mid] = x
UA = lambda why: {"unavailable": True, "reason": why}

# ---- 1. matches へ取り込み（既存行は betchannel_event_id で対応づけ・重複させない） ----
by_eid = {v.get("betchannel_event_id"): k for k, v in matches.items() if v.get("betchannel_event_id")}
bc_rows = {}
title_stats = {}
for mid0, ev, swapped in bcmap.mapping(events):
    mid = by_eid.get(ev["event_id"]) or mid0
    name, kind = bcfeed.SPORTS[ev["sport_id"]]
    ts = title_stats.setdefault(name, dict(events=0, priced=0, outright=0, new=0, mapped=0, deep=0))
    ts["events"] += 1
    if ev["outright"]:
        ts["outright"] += 1; continue
    if ev["start_jst"] <= LOCKED:
        continue
    ts["priced"] += int(bool(ev["odds"]))
    flags = []
    comp = ev["competition"]
    if "Streamers" in comp: flags.append("ショーマッチ")
    if ev["sport_id"] == 110 and "EMEA Masters" in comp: flags.append("BO1")
    if ev["sport_id"] == 125 and ("League" in comp or "APL" in comp) and "Final" not in comp: flags.append("BO1")
    if "Urban Riga" in comp: flags.append("BO1")
    if any(w in comp for w in ("United21", "European Pro League", "EPIC Jumble")): flags.append("下位リーグ（整合性リスク）")
    if ev["sport_id"] == 230: flags.append("下位リーグ（整合性リスク）")   # Standoff 2：結果DBがなく大会情報も薄い
    if mid in matches:
        ts["mapped"] += 1
        m = matches[mid]
        if m["left"] != ev["left"] or m["right"] != ev["right"]:
            m["note"] = (m.get("note") or "") + f"／BET CHANNEL表記に統一（旧：{m['left']} vs {m['right']}）"
        if m["start_jst"] != ev["start_jst"]:
            m["note"] = (m.get("note") or "") + f"／開始時刻をBET CHANNEL掲載の{ev['start_jst'][5:16]}に訂正"
        m.update(left=ev["left"], right=ev["right"], start_jst=ev["start_jst"])
        m["flags"] = sorted(set(m.get("flags", [])) | set(flags))
        m["betchannel_event_id"] = ev["event_id"]
    else:
        ts["new"] += 1
        matches[mid] = dict(sport=name, competition=comp, round=None, start_jst=ev["start_jst"],
                            left=ev["left"], right=ev["right"], home_away="中立（オンライン/大会会場）", status="scheduled",
                            result=None, note=f"BET CHANNEL event_id={ev['event_id']}（{taken[11:16]}取得）", flags=sorted(set(flags)),
                            betchannel_event_id=ev["event_id"])
    bc_rows[mid] = ev
    if ev["odds"]:
        o = ev["odds"]
        prices = {"L": o["L"], "R": o["R"]} if o["D"] is None else {"L": o["L"], "D": o["D"], "R": o["R"]}
        odds.append(dict(match_id=mid, taken_at=taken, source=f"BET CHANNEL（{BC_VIA} event_id={ev['event_id']} market={o['market_id']}）",
                         market=o["market"], prices=prices, exact=True, book_verified=True))

# ---- 2. facts の読み込み（今回の対象試合すべて） ----
for mid in bc_rows:
    _load_facts(mid)
    if mid in dd:
        sp = matches[mid]["sport"]
        title_stats.setdefault(sp, dict(events=0, priced=0, outright=0, new=0, mapped=0, deep=0))["deep"] += 1

inventory = sorted([mid for mid, m in matches.items() if m["start_jst"] > LOCKED], key=lambda k: matches[k]["start_jst"])
HARD = {"ショーマッチ", "BO1", "開始時刻要確認", "下位リーグ（整合性リスク）", "シミュレーション/バーチャル（実力データなし）",
        "バトルロイヤル（1対1の勝敗市場なし）", "価格が実力差と不整合", "価格が実力差と不整合の可能性", "消化試合",
        "主力休養リスク", "短期戦フォーマット", "控え中心の編成", "対戦相手未確定"}
DIV = 15  # 内製log5と市場の乖離がこれを超えたら正式採用しない


def s1(v, why):
    if v is None or v == "" or v == []:
        return UA(why)
    if isinstance(v, list):
        return "／".join(str(t) for t in v[:8])
    if isinstance(v, dict):
        return v
    return v


def facts_summary(x):
    L, R = x.get("left") or {}, x.get("right") or {}
    es = x.get("esports") or {}
    fr = lambda side: f"{side.get('name')}：直近{len(side.get('form') or [])}試合を取得"
    return dict(
        ranking=s1(" ／ ".join(f"{s.get('name')}：{s.get('ranking')}" for s in (L, R) if s.get("ranking")), "順位情報なし"),
        h2h=(f"直接対戦{len(x.get('h2h') or [])}件を取得（詳細は事実欄）" if x.get("h2h") else s1(None, str((x.get("unavailable") or {}).get("h2h") or "対戦記録なし"))),
        recent_form=f"{fr(L)}／{fr(R)}（詳細は事実欄の縦リスト）",
        lineup=s1((L.get("lineup") or []) + (R.get("lineup") or []), "メンバー情報なし"),
        venue=s1(x.get("venue"), "会場情報なし"),
        format=s1(es.get("format"), "取得できず"), lan_online=s1(es.get("lan_online"), "取得できず"),
        roster=s1(es.get("roster") or (L.get("lineup") or [None])[0], "ロスター変更情報なし"),
        map_pool=s1(es.get("map_pool"), "取得できず"), veto=s1(es.get("veto"), "取得できず"),
        patch=s1(es.get("patch"), "取得できず"), series_h2h=s1(es.get("series_h2h") or (f"H2H {len(x.get('h2h') or [])}件" if x.get("h2h") else None), "対戦記録なし"),
        map_h2h=s1(es.get("map_h2h"), "取得できず"), rating=s1(es.get("rating"), "取得できず"),
        risks=s1(x.get("risks"), "リスク記載なし"), missing=s1(x.get("missing"), "不足なし"),
        source_urls=x.get("source_urls") or UA("出典なし"), data_as_of=x.get("data_as_of"))


def detail(mid, ev, ext):
    m = matches[mid]; o = ev["odds"]
    d = dict(title=m["sport"], competition=m["competition"], date=m["start_jst"][:10], start_jst=m["start_jst"],
             matchup=f'{m["left"]} vs {m["right"]}',
             odds=dict(book="BET CHANNEL", via=f"{BC_VIA} event_id={ev['event_id']}", taken_at=taken, market=o["market"],
                       L=o["L"], D=o["D"], R=o["R"], exact=True, betchannel_event_id=ev["event_id"]),
             odds_exact=True, external_market=UA("BET CHANNEL以外のブックとの比較は未実施"))
    d.update(facts_summary(dd[mid]))
    d.update(ext)
    return d


def entry(lg, mid, side, o, prior, why):
    m = matches[mid]; ev = bc_rows[mid]
    if not core.within_horizon(LOCKED, m["start_jst"]):
        return None   # 24時間ルール：ロックから24時間より先の試合は正式採用しない
    eid = core.next_entry_id(ledgers[lg] + [e for e in new_entries[lg] if e], lg, mid, side)
    if eid is None:
        return None
    return dict(entry_id=eid, match_id=mid, market=ev["odds"]["market"],
                selection=m["left"] if side == "L" else m["right"], selection_key=side, stake=core.STAKE,
                odds_taken=o, locked_at=LOCKED, odds_source=f"BET CHANNEL（{taken[11:16]}取得・event_id={ev['event_id']}）",
                prior_prob=round(prior, 4), rationale=why, result=None)


rows = {lg: [] for lg in core.LOGICS}
new_entries = {lg: [] for lg in core.LOGICS}
for mid in inventory:
    m = matches[mid]
    ev = bc_rows.get(mid)
    prevs = {lg: ana_prev[lg].get(mid) for lg in core.LOGICS}
    if ev is None:   # 今回のBET CHANNEL控えにない試合は前回判定を引き継ぐ
        for lg in core.LOGICS:
            r = copy.deepcopy(prevs[lg]) if prevs[lg] else dict(match_id=mid, status="nodata", reason="オッズ未取得", deep_dive=False)
            rows[lg].append(r)
        continue
    flags = set(m.get("flags", []))
    hard = sorted(flags & HARD)
    if mid in dd:   # 片側でも公式戦の実績が取れないチームは判定材料不足として正式採用しない
        for side, lab in (("left", m["left"]), ("right", m["right"])):
            if not ((dd[mid].get(side) or {}).get("form") or []):
                hard.append(f"実績データなし（{lab}）")
    name = lambda k: m["left"] if k == "L" else m["right"]
    if not ev["odds"]:
        for lg in core.LOGICS:
            rows[lg].append(dict(match_id=mid, status="nodata", reason="BET CHANNELで勝敗市場の価格が出ていない", deep_dive=False, priced=False))
        continue
    prices = {"L": ev["odds"]["L"], "R": ev["odds"]["R"]}
    if ev["odds"]["D"]: prices["D"] = ev["odds"]["D"]
    nv, over = core.no_vig(prices)
    fav = min(("L", "R"), key=lambda s: prices[s]); fo = prices[fav]; gap = round(nv[fav] * 100)
    deep = mid in dd
    md, mwhy = model.log5(dd[mid]) if deep else (None, "深掘り未実施（開始まで72時間超のため直前の定時更新で徹底取得）")
    if md:
        md["p"] = {"L": md["prob"], "R": 1 - md["prob"]}
    for lg in core.LOGICS:
        r = dict(match_id=mid, deep_dive=deep, priced=True)
        if not deep:
            if lg == "r1":
                r.update(pick=name(fav), odds=fo, gap=gap, nv=round(nv[fav]*100, 1), overround=round(over*100, 1))
                if fo < 1.05: r.update(status="rejected", reason=f"リターン過小（{fo}）")
                elif fo > 1.45: r.update(status="rejected", reason=f"格差不足（本命{fo}・適正勝率{nv[fav]*100:.0f}%）")
                elif gap >= 70: r.update(status="watch", reason=f"一次通過（格差{gap}）・{mwhy}")
                else: r.update(status="rejected", reason=f"格差{gap}（基準70未満）")
            elif lg == "r2":
                r.update(status="excluded", pick=name(fav), odds=fo, need=round(100/fo, 1), reason=f"独立勝率なし：{mwhy}")
            elif lg == "r3":
                cand = [s for s in ("L", "R") if 1.50 <= prices[s] <= 3.00]
                if not cand: r.update(status="excluded", pick=name(fav), odds=fo, reason="対象価格帯（1.50〜3.00）の選択肢なし")
                else:
                    k = max(cand, key=lambda s: prices[s])
                    r.update(status="excluded", pick=name(k), odds=prices[k], need=round(100/prices[k], 1), reason=f"独立推定なし：{mwhy}")
            else:
                r.update(status="rejected", pick=name(fav), odds=fo, fair=round(nv[fav]*100, 1), reliability="low",
                         reason=f"独立ベース確率なし：{mwhy}（市場確率の流用は禁止）")
            rows[lg].append(r); continue
        # ---------- 徹底取得済み：ロジック別に独立判定 ----------
        if lg == "r1":
            r.update(pick=name(fav), odds=fo, nv=round(nv[fav]*100, 1), gap=gap, overround=round(over*100, 1))
            ext = dict(required_prob=round(1/fo, 4), prior_prob=round(nv[fav], 4), edge_or_ev=f"格差{gap}",
                       rationale=f"①：{name(fav)} {fo}（BET CHANNEL）。控除後の適正勝率{nv[fav]*100:.1f}%。" + (f"リスク：{'・'.join(hard)}" if hard else "重大なリスク要因なし"))
            if fo < 1.05: r.update(status="rejected", reason=f"リターン過小（{fo}）")
            elif fo > 1.45: r.update(status="rejected", reason=f"格差不足（本命{fo}）")
            elif hard: r.update(status="watch", reason="徹底取得済み・リスク要因：" + "・".join(hard))
            elif gap >= 70:
                r.update(status="accepted", reason=f"格差{gap}・BET CHANNEL {fo}で正式採用")
                new_entries[lg].append(entry(lg, mid, fav, fo, nv[fav], ext["rationale"]))
            elif gap >= 63: r.update(status="watch", reason=f"格差{gap}（基準70未満）")
            else: r.update(status="rejected", reason=f"格差{gap}")
        elif lg == "r2":
            if not md:
                r.update(status="excluded", pick=name(fav), odds=fo, need=round(100/fo, 1), reason=f"独立モデル作成不可：{mwhy}")
                ext = dict(required_prob=round(1/fo, 4), prior_prob=UA(mwhy), edge_or_ev=UA(mwhy), rationale="②：" + mwhy)
            else:
                W = 0.08
                best = max(("L", "R"), key=lambda s: md["p"][s]*prices[s]); o = prices[best]; p = md["p"][best]
                evm, evl, evh = p*o-1, (p-W)*o-1, (p+W)*o-1
                r.update(pick=name(best), odds=o, need=round(100/o, 1), est=f"{(p-W)*100:.1f}〜{(p+W)*100:.1f}%",
                         ev_range=f"{evl*100:+.1f}〜{evh*100:+.1f}%")
                ext = dict(required_prob=round(1/o, 4), prior_prob=round(p, 4), edge_or_ev=f"EV{evm*100:+.1f}%",
                           rationale=f"②：{md['method']}。{md['inputs']}。{name(best)}勝率{p:.3f}を±{W}の幅で評価、必要勝率{1/o:.3f}。")
                gapm = abs(p - nv[best]) * 100
                if gapm > DIV or p > nv[best] * 1.6 or evm > 0.25:
                    r.update(status="watch", reason=f"内製モデルと市場の乖離が過大（{gapm:.0f}pt・モデル{p*100:.0f}%対市場{nv[best]*100:.0f}%・中央EV{evm*100:+.1f}%）：相手の強さ未補正log5の歪みの可能性があり正式採用しない")
                elif evl >= 0 and evm >= 0.02 and not hard:
                    r.update(status="formal", reason=f"レンジ下限でもEV{evl*100:+.1f}%")
                    new_entries[lg].append(entry(lg, mid, best, o, p, ext["rationale"]))
                elif evl >= 0 and evm >= 0.02:
                    r.update(status="conditional", reason="EV条件は満たすがリスク要因：" + "・".join(hard))
                elif evh >= 0.02:
                    r.update(status="watch", reason=f"レンジ上側のみプラス（中央EV{evm*100:+.1f}%）")
                else:
                    r.update(status="excluded", reason=f"レンジ全体で必要勝率未満（中央EV{evm*100:+.1f}%）")
        elif lg == "r3":
            cand = [s for s in ("L", "R") if 1.50 <= prices[s] <= 3.00]
            if not cand:
                r.update(status="excluded", pick=name(fav), odds=fo, reason="対象価格帯（1.50〜3.00）の選択肢なし")
                ext = dict(required_prob=round(1/fo, 4), prior_prob=UA("価格帯外"), edge_or_ev=UA("価格帯外"), rationale="③：価格帯外")
            elif not md:
                k = cand[0]
                r.update(status="excluded", pick=name(k), odds=prices[k], need=round(100/prices[k], 1), reason=f"独立推定なし：{mwhy}")
                ext = dict(required_prob=round(1/prices[k], 4), prior_prob=UA(mwhy), edge_or_ev=UA(mwhy), rationale="③：市場差を測れない（" + mwhy + "）")
            else:
                k = max(cand, key=lambda s: md["p"][s] - nv[s]); o = prices[k]
                diff = (md["p"][k] - nv[k]) * 100; ev_ = md["p"][k]*o - 1
                risk = "高" if hard else "中" if o < 1.8 else "中〜高" if o < 2.4 else "高"
                r.update(pick=name(k), odds=o, need=round(100/o, 1), est=f"{md['p'][k]*100:.1f}%", diff=f"{diff:+.1f}pt", upset=risk)
                ext = dict(required_prob=round(1/o, 4), prior_prob=round(md["p"][k], 4), edge_or_ev=f"市場差{diff:+.1f}pt／EV{ev_*100:+.1f}%",
                           rationale=f"③：市場ベースライン{nv[k]*100:.1f}%に対し直近成績log5は{md['p'][k]*100:.1f}%。Upset Risk {risk}。")
                if abs(diff) > DIV:
                    r.update(status="watch" if diff > 0 else "excluded", reason=f"市場差{diff:+.1f}pt（{DIV}pt超は内製モデルの歪みの可能性があり正式採用しない）")
                elif diff >= 3 and 0.02 <= ev_ <= 0.20 and risk != "高":
                    r.update(status="adopted", reason=f"市場差{diff:+.1f}pt・EV{ev_*100:+.1f}%・リスク{risk}")
                    new_entries[lg].append(entry(lg, mid, k, o, md["p"][k], ext["rationale"]))
                elif diff >= 1.5:
                    r.update(status="watch", reason=f"市場差{diff:+.1f}pt・EV{ev_*100:+.1f}%・リスク{risk}")
                else:
                    r.update(status="excluded", reason=f"市場差{diff:+.1f}pt")
        else:
            if not md:
                r.update(status="rejected", pick=name(fav), odds=fo, fair=round(nv[fav]*100, 1), reliability="low",
                         reason=f"独立ベース確率なし：{mwhy}（市場確率の流用は禁止）")
                ext = dict(required_prob=round(1/fo, 4), prior_prob=UA(mwhy), edge_or_ev=UA(mwhy), rationale="④：" + mwhy)
            else:
                fin = {s: 0.5*nv[s] + 0.5*md["p"][s] for s in ("L", "R")}
                k = max(("L", "R"), key=lambda s: fin[s]*prices[s]); o = prices[k]
                edge = (fin[k] - nv[k]) * 100; ev_ = fin[k]*o - 1
                rel = "low" if hard else "medium"
                r.update(pick=name(k), odds=o, fair=round(nv[k]*100, 1), final=round(fin[k]*100, 1), edge=f"{edge:+.1f}pt",
                         ev=f"{ev_*100:+.1f}%", min_odds=math.ceil(100/fin[k])/100, reliability=rel,
                         base_prob=round(md["p"][k], 4), market_prob=round(nv[k], 4))
                ext = dict(required_prob=round(1/o, 4), prior_prob=round(fin[k], 4), edge_or_ev=f"EDGE{edge:+.1f}pt／EV{ev_*100:+.1f}%",
                           rationale=f"④：market {nv[k]:.3f}（no-vig）＋base {md['p'][k]:.3f}（直近成績log5）を等分、expert_adjustment 0 → final {fin[k]:.3f}。")
                if abs(md["p"][k] - nv[k]) * 100 > DIV or fin[k] > nv[k] * 1.5 or ev_ > 0.15:
                    r.update(status="watch" if edge >= 1.5 else "rejected", reason=f"base（内製log5）と市場の乖離が過大（{abs(md['p'][k]-nv[k])*100:.0f}pt・EV{ev_*100:+.1f}%）：正式採用しない")
                elif edge >= 3 and ev_ >= 0.03 and rel != "low":
                    r.update(status="accepted", reason=f"EDGE{edge:+.1f}pt・EV{ev_*100:+.1f}%")
                    new_entries[lg].append(entry(lg, mid, k, o, fin[k], ext["rationale"]))
                elif edge >= 1.5 and ev_ > -0.01:
                    r.update(status="watch", reason=f"EDGE{edge:+.1f}pt・EV{ev_*100:+.1f}%（基準未達）")
                else:
                    r.update(status="rejected", reason=f"EDGE{edge:+.1f}pt・EV{ev_*100:+.1f}%")
        for k2 in ("required_prob", "prior_prob", "edge_or_ev", "rationale"):
            ext.setdefault(k2, UA("算出不可"))
        r["rationale"] = ext["rationale"]
        r["deep_dive_detail"] = detail(mid, ev, ext)
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
    new_entries[lg] = [e for e in new_entries[lg] if e and e["entry_id"] not in have]
    core.save(f"ledger/{lg}.json", ledgers[lg] + new_entries[lg])

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
        lc = coverage[sp].setdefault(lg, dict(screened=0, deep_dive=0, formal=0, watch=0, rejected=0, nodata=0))
        lc["screened"] += 1; lc["deep_dive"] += int(bool(r.get("deep_dive")))
        s = r["status"]
        lc["formal" if s == FORMAL[lg] else "watch" if s in ("watch", "conditional") else "nodata" if s == "nodata" else "rejected"] += 1
for sp, c in coverage.items():
    for lg in core.LOGICS:
        lc = c[lg]
        if c["priced_upcoming_count"] and not lc["deep_dive"]:
            lc["deep_dive_waiver"] = "開始まで48時間超の試合のみ（King of Glory・MPL・ESL Pro League等）。直前の定時更新で徹底取得する"
runs = core.load("automation-runs.json")
prev = runs[-1]
gone = {sp: "対象時間内に未開始の試合なし（全試合開始済み）" for sp in prev["coverage"] if sp not in coverage}
CL = dict(prev["checklist"]); notes = dict(prev.get("checklist_notes", {}))
notes["05"] = "eスポーツ：BET CHANNEL実チーム系の72時間以内・価格ありの全試合を徹底取得（直近10試合・H2H・60日共通相手）して①〜④判定。King of Glory・MPL等の72時間超は一次判定"
run = dict(run_id=RUN_ID, slot="23:20（追加・eスポーツ72時間分の徹底判定）", started_at=STARTED, finished_at=core.now_jst(), start_sha=START_SHA,
           status="partial", previous_run_ok=False, carried_blockers=prev.get("blockers", []),
           inventory_match_ids=inventory, coverage=coverage, sports_disappeared=gone,
           sources=dict(prev["sources"], betchannel=f"取得：LIVEスポーツprematch配信の実チーム系eスポーツ全{len(events)}件（{taken[11:16]}取得、控え {BC_FILE}）。シミュレーション系（FC26・eサッカー等）は本枠では未取り込み（次回定時更新で取得）"),
           esports_deep=dict(taken_at=taken, facts_files=len(dd), by_title={k: v for k, v in title_stats.items()}),
           blockers=[b for b in prev.get("blockers", []) if "eスポーツ" not in b] +
                    ["eスポーツ：72時間超の試合（King of Glory・MPL・ESL Pro League・NA/SA/CN League・R6 10/5等）は一次判定のみ（直前の定時更新で徹底取得）",
                     "シミュレーション系（FC26・eサッカー等）の今回分は未取り込み（定時更新で取得）"],
           checklist=CL, checklist_notes=notes)
runs.append(run)
core.save("automation-runs.json", runs)
build()
for lg in core.LOGICS:
    print(lg, [(e["selection"], e["odds_taken"], matches[e["match_id"]]["sport"]) for e in new_entries[lg]])
print("inventory", len(inventory), "deepfacts", len(dd))
for n, s in sorted(title_stats.items()):
    print(n, s)
