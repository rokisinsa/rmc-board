"""06:00枠 定時更新（10-02・PCオフ・クラウド実行）。run_20260929_1800.py を雛形にし、⑤（rmc.discover）との連携・競技枠（rmc.select.apply_floor）を追加。
- 結果確認（/home/claude/dd/res/auto.json＝LiveScore・tennisexplorer の自動照合、out_*.json＝サブエージェント）を matches に反映し、同じ match_id の全ロジック・経験値取引を精算。
- 公開配信（odds-fetch を workflow_dispatch で再取得）を scripts/run_20261002_0600_ingest.py --no-new で既存試合に対応づけ、単一ブックの exact odds で ①〜④ を独立判定。
- 深掘り＝data/facts（⑤の完全深掘り・過去の深掘り・LiveScore/tennisexplorer の自動取得行データ）。24時間以内・価格ありで facts の無い試合は自動取得の行データから facts を追補。
- 独立勝率：テニスは Tennis Abstract Elo（外部モデル・data/ratings）、それ以外は rmc/model.py の log5（内製）。サッカー1X2は3択の独立モデルが無いので②③④は通常基準では判定しない。
- ⑤の結果を rmc.discover.tag_rows で各行に付け、通常基準0件の競技は rmc.select.apply_floor で競技枠。
使い方: python scripts/run_20261002_0600.py <ロック時刻JST>"""
import copy, glob, json, math, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core, model, select, discover as D

RUN_ID = "run-20261002-0600"
STARTED = "2026-10-02T05:56:14+09:00"
START_SHA = "e8e26f3"
LOCKED = sys.argv[1]
DD = "/home/claude/dd"
DIV = 15
H24 = core.parse(LOCKED).timestamp() + 24 * 3600
UA = lambda why: {"unavailable": True, "reason": why}
SR = {1: "official_team", 2: "league_official", 3: "results_db", 4: "livescore"}

matches = core.load("matches.json")
odds = core.load("odds_snapshots.json")
ana_prev = {lg: {r["match_id"]: r for r in core.load(f"analysis/{lg}.json")["rows"]} for lg in core.LOGICS}
ledgers = {lg: core.load(f"ledger/{lg}.json", []) for lg in core.LOGICS + ("experience",)}
scr = core.load("discovery/latest.json")
ratings = D.load_ratings()

# ================= 1. 結果反映・精算 =================
results = json.load(open(f"{DD}/res/auto.json", encoding="utf-8"))
for f in sorted(glob.glob(f"{DD}/res/out_*.json")):
    results += json.load(open(f, encoding="utf-8"))
settled_log, result_log = [], []
for r in results:
    m = matches[r["match_id"]]
    if r["status"] == "final" and r.get("winner") in ("L", "D", "R"):
        m["status"] = "final"
        m["result"] = dict(winner=r["winner"], score=r["score"], source_rank=SR.get(r["source_rank"], r["source_rank"]), source_url=r["source_url"],
                           identity_checked=bool(r.get("identity_checked")), identity_note=r.get("identity_note"),
                           note=r.get("note"), checked_at=LOCKED, run_id=RUN_ID)
        m.pop("result_pending_reason", None)
        result_log.append((r["match_id"], "final", r["score"]))
    elif m["status"] != "final":
        if r["status"] in ("postponed", "cancelled", "abandoned"):
            m["status"] = r["status"]
        m["result_pending_reason"] = f"{LOCKED[:16]} 時点：{r['status']}。{(r.get('note') or '')[:300]}"
        m["note"] = (m.get("note") or "") + f"／{LOCKED[5:16]}時点 {r['status']}：{(r.get('note') or '')[:200]}"
        result_log.append((r["match_id"], r["status"], r.get("note")))
for lg, L in ledgers.items():
    for e in L:
        if e.get("result"):
            continue
        s = core.settle_entry(e, matches[e["match_id"]])
        if s:
            e["result"] = dict(s, settled_at=LOCKED, run_id=RUN_ID)
            settled_log.append((lg, e["entry_id"], e["selection"], e["odds_taken"], s["outcome"], s.get("profit"),
                                matches[e["match_id"]]["result"]["score"] if matches[e["match_id"]].get("result") else ""))

os.makedirs(core.path("reviews"), exist_ok=True)
for lg, eid, sel, o, out, pf, sc in settled_log:
    if out != "loss":
        continue
    e = next(x for x in ledgers[lg] if x["entry_id"] == eid)
    m = matches[e["match_id"]]
    pp = e.get("prior_prob") or 0
    txt = f"""# post-match review: {eid}

- 試合：{m['sport']}／{m['competition']}／{m['start_jst']}／{m['left']} vs {m['right']}
- 採用：{lg} {sel} @ {o}（$100、locked_at {e['locked_at']}、{e['odds_source']}）{'・競技枠' if e.get('pick_type') == 'sport_floor' else ''}
- 事前仮説：{e.get('rationale')}（事前推定勝率 {e.get('prior_prob')}）
- 実際の結果：{sc}（{m['result']['source_url']}、{m['result'].get('identity_note') or ''}）
- 見落とし：深掘り時点（locked_at 以前）の facts には主力欠場・ローテーション等の決定的な記載なし。試合後の情報は事前分析に使わない。
- failure factor：選択側の敗戦。事前推定 {pp} に対し負ける確率は約{(1 - pp) * 100:.0f}%あった。
- 推定勝率の過大評価：1件では判定不能（同ロジック・同競技・同価格帯の実勝率を summary.analytics の推定勝率帯で累積して確認）。
- variance か structural か：現時点では variance と判定（1敗のみ。同種の敗戦が複数そろった時点で基準・較正を再検討）。
- CLV：data/odds_closing.json に締切前オッズがあれば summary.analytics に自動計算。
- roster等の変化：事前の facts で確認できた範囲では記載なし。
- 再発防止仮説：同競技・同価格帯の成績を積み上げ、的中率が推定勝率を有意に下回る場合に基準を見直す。1敗だけでモデル係数は変えない。
- 記録：{RUN_ID}（{LOCKED}）
"""
    open(core.path("reviews", f"{eid}.md"), "w", encoding="utf-8").write(txt)

# ================= 2. 配信（再取得分）=================
feed = json.load(open(f"{DD}/feed_inv.json", encoding="utf-8"))
ing = json.load(open(f"{DD}/ingest.json", encoding="utf-8"))
fid2mid, fid_swapped = ing["fid2mid"], ing["fid_swapped"]
feed_rows = {}
for x in feed:
    mid = fid2mid.get(x["fid"])
    if mid and mid in matches:
        feed_rows[mid] = x


def cur_prices(mid):
    x = feed_rows.get(mid)
    if not x or not x["prices"]:
        return None
    p = dict(x["prices"])
    if fid_swapped.get(x["fid"]):
        p["L"], p["R"] = p["R"], p["L"]
    return p


inventory = sorted([mid for mid, m in matches.items() if m["start_jst"] > LOCKED and m["status"] in ("scheduled", "unknown")],
                   key=lambda k: matches[k]["start_jst"])

# ---- facts の追補：24時間以内・価格ありで facts が無い試合は自動取得の行データ（LiveScore／tennisexplorer）から作る ----
added_facts = []
for mid in inventory:
    m = matches[mid]
    if os.path.exists(core.path("facts", f"{mid}.json")) or not cur_prices(mid) or core.parse(m["start_jst"]).timestamp() > H24:
        continue
    bf = D.basic_facts(m)
    if not bf or not bf["left"]["form"] or not bf["right"]["form"]:
        continue
    taken = (D._BASIC.get("tennis") if m["sport"] == "テニス" else D._BASIC.get("ls")) or {}
    un = {"history": "60日共通相手は直近成績（form）内で照合。自動取得元以外の追加試合は未取得"}
    if not bf["h2h"]:
        un["h2h"] = f"自動取得元（{bf['_basic_source']}）に直接対戦の記録なし（初対戦か収録範囲外）"
    for side in ("left", "right"):
        if len(bf[side]["form"]) < 5:
            un[f"{side}.form"] = f"自動取得元の収録が{len(bf[side]['form'])}試合のみ"
    fx = dict(match_id=mid, data_as_of=taken.get("taken_at") or LOCKED, unit="セット" if m["sport"] == "テニス" else "なし",
              left=dict(name=m["left"], ranking="", form=bf["left"]["form"]), right=dict(name=m["right"], ranking="", form=bf["right"]["form"]),
              h2h=bf["h2h"], common_opponents_notes=[], venue=m.get("home_away") or "", risks=["自動取得の行データのみ（欠場・ロスター等のWeb確認なし）"],
              missing=["欠場・ロスター・先発（Web未確認）"], unavailable=un, source_urls=[bf["_basic_source"]],
              metrics=bf.get("metrics"), current_competition=bf.get("current_competition") or {}, auto_facts=True)
    core.save(f"facts/{mid}.json", fx)
    added_facts.append(mid)

HARD = {"ショーマッチ", "下位リーグ（整合性リスク）", "価格が実力差と不整合", "価格が実力差と不整合の可能性", "消化試合",
        "主力休養リスク", "親善試合（ローテーション）", "高地開催の可能性", "BO1", "短期戦フォーマット", "プレシーズン/カップ戦",
        "控え中心の編成", "開始時刻要確認", "対戦相手未確定", "シミュレーション/バーチャル（実力データなし）", "バトルロイヤル（1対1の勝敗市場なし）"}
ESPORTS = D.ESPORTS | {"eスポーツ（その他）"}
d5rows = {r["match_id"]: r for r in scr["rows"]}


def facts_of(mid):
    p = core.path("facts", f"{mid}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def tennis_elo(m):
    surf = str((D.merged_facts(m["match_id"], m) or {}).get("surface") or "").lower()
    a, b, src = D._lookup2(ratings, "テニス", m["left"], m["right"], "elo")
    if a is None:
        return None, "Tennis Abstract Elo に両者がそろっていない"
    sf = "elo_clay" if "clay" in surf else "elo_grass" if "grass" in surf else "elo_hard" if ("hard" in surf or "indoor" in surf) else None
    sa, sb = (D._lookup2(ratings, "テニス", m["left"], m["right"], sf)[:2] if sf else (None, None))
    ea, eb = ((a + sa) / 2, (b + sb) / 2) if sa is not None and sb is not None else (a, b)
    p = 1 / (1 + 10 ** ((eb - ea) / 400))
    meth = f"Tennis Abstract Elo（{'総合と' + sf + 'の平均' if sa is not None and sb is not None else '総合'}）"
    return dict(prob=p, side="L", method=meth, inputs=f"{src}：{m['left']} {ea:.0f} 対 {m['right']} {eb:.0f}",
                p={"L": p, "R": 1 - p}, internal=False), None


def the_model(mid, fx):
    m = dict(matches[mid], match_id=mid)
    if m["sport"] == "テニス":
        md, why = tennis_elo(m)
        if md:
            return md, None
    if m["sport"] == "サッカー":
        return None, "サッカー1X2は引分けを含む3択の独立モデルが必要（log5は2択のため使わない）"
    md, why = model.log5(fx)
    if md:
        md["p"] = {"L": md["prob"], "R": 1 - md["prob"]}
        md["internal"] = True
    return md, why


def summ(v, why):
    if v is None or v == "" or v == [] or v == {} or (isinstance(v, dict) and v.get("unavailable")):
        return UA(v.get("reason") if isinstance(v, dict) and v.get("reason") else why)
    if isinstance(v, list):
        return "／".join(map(str, v))
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    return v


def form_txt(fx):
    out = []
    for side in ("left", "right"):
        s = fx.get(side) or {}
        rows = s.get("form") or []
        if rows:
            out.append(f"{s.get('name')}：" + "・".join(f"{g.get('date')} {g.get('opp')} {g.get('score')}{g.get('res')}" for g in rows[:10]))
    return out


def detail(mid, ext):
    fx = facts_of(mid) or {}; m = matches[mid]; fr = feed_rows.get(mid); dd = fx.get("deep5") or {}
    p = cur_prices(mid)
    un = fx.get("unavailable") or {}
    ext_mk = UA("Bovada以外のブックの比較値なし（公開配信は1社のみ）")
    if fr and fr.get("books"):
        bk = fr["books"]; sw = fid_swapped.get(fr["fid"])
        ext_mk = "／".join(f"{b} {v[1] if sw else v[0]}-{v[0] if sw else v[1]}" for b, v in list(bk.items())[:8])
    lineup = [x for x in [dd.get("absences"), dd.get("roster_changes")] if x] + list((fx.get("left") or {}).get("lineup") or [])
    d = dict(title=m["sport"], competition=m["competition"], date=m["start_jst"][:10], start_jst=m["start_jst"],
             matchup=f'{m["left"]} vs {m["right"]}',
             ranking=summ(dd.get("ranking") or " ／ ".join(x for x in [(fx.get("left") or {}).get("ranking"), (fx.get("right") or {}).get("ranking")] if x), "順位情報なし（自動取得元に順位表なし）"),
             h2h=summ(dd.get("h2h_all") or [f"{g.get('date')} {g.get('score')}（{g.get('winner')}）" for g in fx.get("h2h") or []], un.get("h2h") or "過去の対戦が見つからない"),
             recent_form=summ(form_txt(fx), "直近成績なし"), venue=summ(fx.get("venue") or m.get("home_away"), "会場情報なし"),
             lineup=summ(lineup, "欠場・メンバー情報はWeb未確認（自動取得の行データのみ）"),
             odds=(dict(book=fr["book"], via=fr["src"], fid=fr["fid"], taken_at=fr["taken_at"], market=fr["market"], exact=True, **p) if p else UA("今回の公開配信に価格なし")),
             odds_exact=True if p else UA("価格なし"), external_market=ext_mk,
             risks=summ(fx.get("risks"), "リスク記載なし"), missing=summ(fx.get("missing") or [f"{k}: {v}" for k, v in un.items()], "不足なし"),
             source_urls=fx.get("source_urls") or UA("出典なし"), data_as_of=min(fx.get("data_as_of") or LOCKED, LOCKED))
    if m["sport"] in ESPORTS:
        es = fx.get("esports") or {}
        for k in ("format", "lan_online", "roster", "map_pool", "veto", "patch", "series_h2h", "map_h2h", "rating"):
            d[k] = summ(es.get(k) or (dd.get("bo_format") if k == "format" else dd.get("lan_online") if k == "lan_online" else None), "取得できず（試合前に未発表または取得元なし）")
    d.update(ext)
    for k in ("required_prob", "prior_prob", "edge_or_ev", "rationale"):
        d.setdefault(k, UA("算出不可"))
    return d


def entry(lg, mid, side, o, prior, why):
    m = matches[mid]; fr = feed_rows[mid]
    if not core.within_horizon(LOCKED, m["start_jst"]):
        return None
    eid = core.next_entry_id(ledgers[lg] + [e for e in new_entries[lg] if e], lg, mid, side)
    if eid is None:
        return None
    return dict(entry_id=eid, match_id=mid, market=fr["market"],
                selection=m["left"] if side == "L" else m["right"], selection_key=side, stake=core.STAKE,
                odds_taken=o, locked_at=LOCKED, odds_source=f"{fr['book']}（{fr['src']}・{fr['taken_at'][11:16]}取得・{fr['fid']}）",
                prior_prob=round(prior, 4), rationale=why, result=None)


def dup_note(r, m):
    if not core.within_horizon(LOCKED, m["start_jst"]):
        r.update(status="watch", reason="基準を満たすが開始がロックから24時間超（次回以降の定時更新で再判定）：" + str(r.get("reason")))
    else:
        r["reason"] = str(r.get("reason")) + "（同じ選択の正式採用は前回までに記録済み・重複追加なし）"


rows = {lg: [] for lg in core.LOGICS}
new_entries = {lg: [] for lg in core.LOGICS}
for mid in inventory:
    m = matches[mid]
    p = cur_prices(mid)
    fx = facts_of(mid)
    deep = bool(fx and (fx.get("left") or {}).get("form") and (fx.get("right") or {}).get("form")) and m["start_jst"] > LOCKED
    if fx and fx.get("data_as_of") and fx["data_as_of"] >= m["start_jst"]:
        deep = False   # 開始後のデータしか無い facts は事前分析に使わない
    if not p:
        for lg in core.LOGICS:
            r = dict(match_id=mid, status="nodata", deep_dive=deep, priced=False,
                     reason=("公開配信（Bovada/tennisexplorer）に価格なし" + ("（⑤の日程ソースから登録した試合・深掘り済み）" if deep else "")))
            if deep:
                r["deep_dive_detail"] = detail(mid, dict(rationale=f"{lg}：価格がないため判定不能（事実のみ記録）"))
            rows[lg].append(r)
        continue
    flags = set(m.get("flags", []))
    hard = sorted(flags & HARD)
    if deep:
        for side_, lab_ in (("left", m["left"]), ("right", m["right"])):
            nf = len((fx.get(side_) or {}).get("form") or [])
            if nf < 5:
                hard.append(f"事実不足（{lab_}の直近成績{nf}試合）")
        d5 = d5rows.get(mid) or {}
        if d5.get("status") == "反対材料で保留":
            hard.append("⑤：格差を崩す反対材料あり（" + str(d5.get("reason"))[:60] + "）")
    name = lambda k: m["left"] if k == "L" else m["right"] if k == "R" else "引分け"
    nv, over = core.no_vig(p)
    fav = min(("L", "R"), key=lambda s: p[s]); fo = p[fav]; gap = round(nv[fav] * 100)
    within = core.parse(m["start_jst"]).timestamp() <= H24
    md, mwhy = the_model(mid, fx) if deep else (None, "深掘り未実施")
    book = feed_rows[mid]["book"]
    for lg in core.LOGICS:
        r = dict(match_id=mid, deep_dive=deep, priced=True)
        if not deep:
            lack = "開始まで24時間超：直前の定時更新で深掘りしてから判定する" if not within else "深掘り未実施（自動取得元に行データがなく、Web深掘り枠外）"
            if lg == "r1":
                r.update(pick=name(fav), odds=fo, gap=gap, nv=round(nv[fav] * 100, 1), overround=round(over * 100, 1))
                if fo < 1.05: r.update(status="rejected", reason=f"リターン過小（{fo}）")
                elif fo > 1.45: r.update(status="rejected", reason=f"格差不足（本命{fo}・適正勝率{nv[fav]*100:.0f}%）")
                elif gap >= 70: r.update(status="watch", reason=f"一次通過（格差{gap}）・{lack}")
                else: r.update(status="rejected", reason=f"格差{gap}（基準70未満・本命{fo}）")
            elif lg == "r2":
                r.update(status="excluded", pick=name(fav), odds=fo, need=round(100 / fo, 1), reason=f"独立勝率なし：{lack}（必要勝率{100/fo:.1f}%のみ算出）")
            elif lg == "r3":
                cand = [s for s in ("L", "R") if 1.50 <= p[s] <= 3.00]
                if not cand:
                    r.update(status="excluded", pick=name(fav), odds=fo, reason=f"対象価格帯（1.50〜3.00）の選択肢なし（本命{fo}）")
                else:
                    k = max(cand, key=lambda s: p[s])
                    r.update(status="excluded", pick=name(k), odds=p[k], need=round(100 / p[k], 1), reason=f"市場差を測る独立推定なし：{lack}（市場ベースライン{nv[k]*100:.1f}%）")
            else:
                r.update(status="rejected", pick=name(fav), odds=fo, fair=round(nv[fav] * 100, 1), reliability="low", reason=f"独立ベース確率なし：{lack}（市場確率の流用は禁止）")
            rows[lg].append(r); continue
        mname = (md or {}).get("method", "")
        if lg == "r1":
            r.update(pick=name(fav), odds=fo, nv=round(nv[fav] * 100, 1), gap=gap, overround=round(over * 100, 1))
            ext = dict(required_prob=round(1 / fo, 4), prior_prob=round(nv[fav], 4), edge_or_ev=f"格差{gap}",
                       rationale=f"①：{name(fav)} {fo}（{book}）。控除後の適正勝率{nv[fav]*100:.1f}%。" + (f"リスク：{'・'.join(hard)}" if hard else "重大なリスク要因なし"))
            if fo < 1.05: r.update(status="rejected", reason=f"リターン過小（{fo}）")
            elif fo > 1.45: r.update(status="rejected", reason=f"格差不足（本命{fo}）")
            elif hard: r.update(status="watch", reason="深掘り済み・リスク要因：" + "・".join(hard))
            elif gap >= 70:
                r.update(status="accepted", reason=f"格差{gap}・{book} {fo}で正式採用")
                _e = entry(lg, mid, fav, fo, nv[fav], ext["rationale"])
                if _e: new_entries[lg].append(_e)
                else: dup_note(r, m)
            elif gap >= 63: r.update(status="watch", reason=f"格差{gap}（基準70未満）")
            else: r.update(status="rejected", reason=f"格差{gap}")
        elif lg == "r2":
            if not md:
                r.update(status="excluded", pick=name(fav), odds=fo, need=round(100 / fo, 1), reason=f"独立モデルなし：{mwhy}")
                ext = dict(required_prob=round(1 / fo, 4), prior_prob=UA(mwhy), edge_or_ev=UA(mwhy), rationale="②：" + mwhy)
            else:
                W = 0.08 if md["internal"] else 0.04
                best = max([s for s in md["p"] if s in p], key=lambda s: md["p"][s] * p[s]); o = p[best]; q = md["p"][best]
                evm, evl, evh = q * o - 1, (q - W) * o - 1, (q + W) * o - 1
                r.update(pick=name(best), odds=o, need=round(100 / o, 1), est=f"{(q-W)*100:.1f}〜{(q+W)*100:.1f}%", ev_range=f"{evl*100:+.1f}〜{evh*100:+.1f}%")
                ext = dict(required_prob=round(1 / o, 4), prior_prob=round(q, 4), edge_or_ev=f"EV{evm*100:+.1f}%",
                           rationale=f"②：{mname[:50]}。{md.get('inputs','')[:90]}。{name(best)}勝率{q:.3f}を±{W}で評価、必要勝率{1/o:.3f}。")
                gapm = abs(q - nv[best]) * 100
                if md.get("internal") and (q > nv[best] * 1.6 or evm > 0.25):
                    r.update(status="watch", reason=f"内製log5と市場の乖離が過大（モデル{q*100:.0f}%対市場{nv[best]*100:.0f}%・中央EV{evm*100:+.1f}%）：相手の強さ未補正の歪みの可能性があり正式採用しない")
                elif gapm > DIV:
                    r.update(status="watch", reason=f"モデルと市場の乖離{gapm:.0f}pt（{DIV}pt超は情報不足・モデル歪みの可能性があり正式採用しない）・中央EV{evm*100:+.1f}%")
                elif evl >= 0 and evm >= 0.02 and not hard:
                    r.update(status="formal", reason=f"レンジ下限でもEV{evl*100:+.1f}%")
                    _e = entry(lg, mid, best, o, q, ext["rationale"])
                    if _e: new_entries[lg].append(_e)
                    else: dup_note(r, m)
                elif evl >= 0 and evm >= 0.02:
                    r.update(status="conditional", reason="EV条件は満たすがリスク要因：" + "・".join(hard))
                elif evh >= 0.02:
                    r.update(status="watch", reason=f"レンジ上側のみプラス（中央EV{evm*100:+.1f}%）")
                else:
                    r.update(status="excluded", reason=f"レンジ全体で必要勝率未満（中央EV{evm*100:+.1f}%）")
        elif lg == "r3":
            cand = [s for s in ("L", "R") if 1.50 <= p[s] <= 3.00]
            if not cand:
                r.update(status="excluded", pick=name(fav), odds=fo, reason=f"対象価格帯（1.50〜3.00）の選択肢なし（本命{fo}）")
                ext = dict(required_prob=round(1 / fo, 4), prior_prob=UA("価格帯外"), edge_or_ev=UA("価格帯外"), rationale="③：価格帯外（1.50〜3.00の選択肢なし）")
            elif not md:
                k = cand[0]
                r.update(status="excluded", pick=name(k), odds=p[k], need=round(100 / p[k], 1), reason=f"独立推定なし：{mwhy}")
                ext = dict(required_prob=round(1 / p[k], 4), prior_prob=UA(mwhy), edge_or_ev=UA(mwhy), rationale=f"③：市場ベースライン{nv[k]*100:.1f}%との差を測る独立推定なし（{mwhy}）")
            else:
                k = max(cand, key=lambda s: md["p"][s] - nv[s]); o = p[k]
                diff = (md["p"][k] - nv[k]) * 100; ev_ = md["p"][k] * o - 1
                risk = "高" if hard else "中" if o < 1.8 else "中〜高" if o < 2.4 else "高"
                r.update(pick=name(k), odds=o, need=round(100 / o, 1), est=f"{md['p'][k]*100:.1f}%", diff=f"{diff:+.1f}pt", upset=risk)
                ext = dict(required_prob=round(1 / o, 4), prior_prob=round(md["p"][k], 4), edge_or_ev=f"市場差{diff:+.1f}pt／EV{ev_*100:+.1f}%",
                           rationale=f"③：市場ベースライン{nv[k]*100:.1f}%に対し{mname[:30]}は{md['p'][k]*100:.1f}%。Upset Risk {risk}。")
                if abs(diff) > DIV:
                    r.update(status="watch" if diff > 0 else "excluded", reason=f"市場差{diff:+.1f}pt（{DIV}pt超はモデル歪みの可能性があり正式採用しない）")
                elif diff >= 3 and ev_ >= 0.02 and risk != "高" and not (md.get("internal") and ev_ > 0.20):
                    r.update(status="adopted", reason=f"市場差{diff:+.1f}pt・EV{ev_*100:+.1f}%・リスク{risk}")
                    _e = entry(lg, mid, k, o, md["p"][k], ext["rationale"])
                    if _e: new_entries[lg].append(_e)
                    else: dup_note(r, m)
                elif diff >= 1.5:
                    r.update(status="watch", reason=f"市場差{diff:+.1f}pt・EV{ev_*100:+.1f}%・リスク{risk}")
                else:
                    r.update(status="excluded", reason=f"市場差{diff:+.1f}pt")
        else:
            if not md:
                r.update(status="rejected", pick=name(fav), odds=fo, fair=round(nv[fav] * 100, 1), reliability="low", reason=f"独立ベース確率なし：{mwhy}（市場確率の流用は禁止）")
                ext = dict(required_prob=round(1 / fo, 4), prior_prob=UA(mwhy), edge_or_ev=UA(mwhy), rationale="④：base_probability なし（" + mwhy + "）")
            else:
                fin = {s: 0.5 * nv[s] + 0.5 * md["p"][s] for s in md["p"] if s in p}
                k = max(fin, key=lambda s: fin[s] * p[s]); o = p[k]
                edge = (fin[k] - nv[k]) * 100; ev_ = fin[k] * o - 1
                rel = "low" if hard else ("medium" if md["internal"] or book == "Bovada" else "high")
                r.update(pick=name(k), odds=o, fair=round(nv[k] * 100, 1), final=round(fin[k] * 100, 1), edge=f"{edge:+.1f}pt",
                         ev=f"{ev_*100:+.1f}%", min_odds=math.ceil(100 / fin[k]) / 100, reliability=rel,
                         base_prob=round(md["p"][k], 4), market_prob=round(nv[k], 4))
                ext = dict(required_prob=round(1 / o, 4), prior_prob=round(fin[k], 4), edge_or_ev=f"EDGE{edge:+.1f}pt／EV{ev_*100:+.1f}%",
                           rationale=f"④：market {nv[k]:.3f}（no-vig）＋base {md['p'][k]:.3f}（{mname[:25]}）を等分、expert_adjustment 0 → final {fin[k]:.3f}。")
                if abs(md["p"][k] - nv[k]) * 100 > DIV or (md.get("internal") and (fin[k] > nv[k] * 1.5 or ev_ > 0.15)):
                    r.update(status="watch" if edge >= 1.5 else "rejected", reason=f"baseと市場の乖離{abs(md['p'][k]-nv[k])*100:.0f}pt：{DIV}pt超は正式採用しない（EDGE{edge:+.1f}pt・EV{ev_*100:+.1f}%）")
                elif edge >= 3 and ev_ >= 0.03 and rel != "low":
                    r.update(status="accepted", reason=f"EDGE{edge:+.1f}pt・EV{ev_*100:+.1f}%")
                    _e = entry(lg, mid, k, o, fin[k], ext["rationale"])
                    if _e: new_entries[lg].append(_e)
                    else: dup_note(r, m)
                elif edge >= 1.5 and ev_ > -0.01:
                    r.update(status="watch", reason=f"EDGE{edge:+.1f}pt・EV{ev_*100:+.1f}%（基準未達）")
                else:
                    r.update(status="rejected", reason=f"EDGE{edge:+.1f}pt・EV{ev_*100:+.1f}%")
        r["rationale"] = ext["rationale"]
        r["deep_dive_detail"] = detail(mid, ext)
        rows[lg].append(r)

# ================= 2.5 ⑤タグ・競技枠 =================
floor_new = {}
for lg in core.LOGICS:
    D.tag_rows(rows[lg], scr)
    new_entries[lg] = [e for e in new_entries[lg] if e]
    fl = select.apply_floor(lg, rows[lg], matches, ledgers[lg] + new_entries[lg], LOCKED)
    floor_new[lg] = fl
    new_entries[lg] += fl

# ================= 3. 保存 =================
core.save("matches.json", matches)
core.save("odds_snapshots.json", odds)
os.makedirs(core.path("snapshots", RUN_ID), exist_ok=True)
for lg in core.LOGICS:
    a = dict(logic=lg, run_id=RUN_ID, run_started_at=STARTED, decided_at=LOCKED, floor_applied_at=LOCKED, rows=rows[lg])
    core.save(f"analysis/{lg}.json", a)
    core.save(f"snapshots/{RUN_ID}/{lg}.json", a)
    have = {e["entry_id"] for e in ledgers[lg]}
    new_entries[lg] = [e for e in new_entries[lg] if e["entry_id"] not in have]
    core.save(f"ledger/{lg}.json", ledgers[lg] + new_entries[lg])
core.save("ledger/experience.json", ledgers["experience"])
core.save(f"snapshots/{RUN_ID}/inventory.json", dict(taken_at=LOCKED, feed_taken_at=sorted({x["taken_at"] for x in feed}),
                                                    match_ids=inventory, feed_ids={k: v for k, v in fid2mid.items()}, duplicates_skipped=ing["dup"]))

FORMAL = core.FORMAL
odds_mids = {o["match_id"] for o in odds}
coverage = {}
for mid in inventory:
    sp = matches[mid]["sport"]
    c = coverage.setdefault(sp, dict(event_count=0, priced_upcoming_count=0, market_count=0, in_24h=0, fresh_priced=0))
    c["event_count"] += 1
    c["in_24h"] += int(core.parse(matches[mid]["start_jst"]).timestamp() <= H24)
    if mid in odds_mids:
        c["priced_upcoming_count"] += 1; c["market_count"] += 1
    c["fresh_priced"] += int(bool(cur_prices(mid)))
for lg in core.LOGICS:
    for r in rows[lg]:
        sp = matches[r["match_id"]]["sport"]
        lc = coverage[sp].setdefault(lg, dict(screened=0, deep_dive=0, formal=0, formal_floor=0, watch=0, rejected=0, nodata=0))
        lc["screened"] += 1; lc["deep_dive"] += int(bool(r.get("deep_dive")))
        s = r["status"]
        lc["formal" if s == FORMAL[lg] else "watch" if s in ("watch", "conditional") else "nodata" if s == "nodata" else "rejected"] += 1
        lc["formal_floor"] += int(s == FORMAL[lg] and r.get("pick_type") == "sport_floor")
for sp, c in coverage.items():
    for lg in core.LOGICS:
        lc = c[lg]
        if c["priced_upcoming_count"] and not lc["deep_dive"]:
            lc["deep_dive_waiver"] = ("今回の公開配信に価格がなく（前回取得値のみ）今回の深掘り対象外" if not c["fresh_priced"]
                                      else "24時間以内の試合がなく、次回以降の定時更新で深掘り" if not c["in_24h"]
                                      else "自動取得元（LiveScore・tennisexplorer）に行データがなく、Web深掘りは⑤のTier1を優先したため枠外（次回の対象）")
runs = core.load("automation-runs.json")
prev = runs[-1]
gone = {sp: "今回の配信・日程ソースに判定時刻以降の未開始試合なし（前回分は開始済み・終了）" for sp in prev["coverage"] if sp not in coverage}
json.dump(dict(rows={lg: len(v) for lg, v in rows.items()},
               new={lg: [(e["selection"], e["odds_taken"], matches[e["match_id"]]["sport"], e["match_id"], e.get("pick_type", "criteria"), matches[e["match_id"]]["start_jst"]) for e in v] for lg, v in new_entries.items()},
               settled=settled_log, results=result_log, inventory=len(inventory), coverage=coverage, gone=gone, dup=ing["dup"], added_facts=added_facts),
          open(f"{DD}/run_out.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("inventory", len(inventory), "settled", len(settled_log), "added_facts", len(added_facts))
for lg in core.LOGICS:
    print(lg, len(new_entries[lg]), [(e["selection"], e["odds_taken"], matches[e["match_id"]]["sport"], e.get("pick_type", "")) for e in new_entries[lg]])
