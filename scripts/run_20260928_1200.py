"""12:00枠 定時更新（PCオフ・クラウド実行）。run_20260928_0600.py と同じ方式。
- 結果確認（/home/claude/dd/results.json）を matches に反映し、同じ match_id の全ロジック・経験値取引を精算。
- GitHub Actions odds-fetch が保存した公開オッズ（Bovada 11:56取得／tennisexplorer 11:59取得、odds-fetch を workflow_dispatch）から、今後24時間の全試合をインベントリに取り込み、
  1試合＝単一ブックの exact odds を odds_snapshots に追記。既存行（日本語名）との対応は /home/claude/dd/mapping.json。
- 競技別サブエージェントの深掘り（/home/claude/dd/out/*.json）で ①〜④ を独立判定し、正式採用を台帳へ追記（append-only）。
- 06:00 に深掘り済みで今回深掘りしない試合は、06:00 の判定をそのまま引き継ぐ（今回の浅い再判定で上書きしない）。
- サッカーは3択の独立モデル（model_prob.p3）があれば②③④に使う。
- ドローから消えたカード（棄権で組合せ変更）は cancelled として void 精算。
使い方: python scripts/run_20260928_1200.py <ロック時刻JST>"""
import copy, glob, hashlib, json, math, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core, model
from rmc.build import build

RUN_ID = "run-20260928-1200"
STARTED = "2026-09-28T11:55:32+09:00"
START_SHA = "6ead576"
LOCKED = sys.argv[1]
DD = "/home/claude/dd"
DIV = 15
H24 = core.parse(LOCKED).timestamp() + 24 * 3600
UA = lambda why: {"unavailable": True, "reason": why}
NOT = {"r1": "rejected", "r2": "excluded", "r3": "excluded", "r4": "rejected"}

matches = core.load("matches.json")
odds = core.load("odds_snapshots.json")
ana_prev = {lg: {r["match_id"]: r for r in core.load(f"analysis/{lg}.json")["rows"]} for lg in core.LOGICS}
ledgers = {lg: core.load(f"ledger/{lg}.json", []) for lg in core.LOGICS + ("experience",)}
feed = json.load(open(f"{DD}/feed_inv.json", encoding="utf-8"))
mapping = {x["fid"]: x for x in json.load(open(f"{DD}/mapping.json", encoding="utf-8"))}
results = json.load(open(f"{DD}/results.json", encoding="utf-8"))
dd = {}
for f in glob.glob(f"{DD}/out/*.json"):
    x = json.load(open(f, encoding="utf-8"))
    dd[x["fid"]] = x

# ================= 1. 結果反映・精算 =================
settled_log = []
# ドロー確認（ATP公式ドロー・raquetc）：プリズミッチ棄権でディミトロフが第9シード枠へ移動 → 登録カード2件は実施されない
for mid_, why in (("m20260928-bb2e4540", "プリズミッチが棄権し、ディミトロフが第9シード枠へ移動。リンコンの1回戦の相手はディミトロフ（09-28 22:30 JST）に変更。登録カード「プリズミッチ vs リンコン」は実施されないため void"),
                  ("m20260928-ce1cb873", "プリズミッチ棄権に伴いディミトロフが別枠へ移動し、グルニエの相手は補欠のオーバーベックに変更。登録カード「グルニエ vs ディミトロフ」は実施されないため void")):
    results.append(dict(match_id=mid_, status="cancelled", note=why + "（ATP公式ドロー https://www.atptour.com/en/scores/current-challenger/porto/9526/draws ・ raquetc 9/27記事で確認）"))
# 開始日の訂正（公式の本日オーダーに含まれず、tennisexplorer 配信は 09-29）
for mid_, st, why in (("m20260928-7ac3f1df", "2026-09-29T18:00:00+09:00", "ATP公式ドローにあり。09-28のオーダーになく、tennisexplorer（id 3333638）は09-29 18:00 JST"),
                      ("m20260928-59f63a04", "2026-09-29T17:00:00+09:00", "ラヤル＝Mark Lajal、プーラン＝Lucas Poullain。ATP公式の09-28オーダーになく（Poullainはダブルスのみ）、tennisexplorer（id 3333556）は09-29 17:00 JST")):
    m_ = matches[mid_]
    if m_["start_jst"] != st and m_["status"] == "scheduled":
        m_["note"] = (m_.get("note") or "") + f"／開始日時を{m_['start_jst'][5:16]}→{st[5:16]}に訂正（{why}。火曜の公式オーダー未発表のため要再確認）"
        m_["start_jst"] = st
        m_["flags"] = sorted(set(m_.get("flags", [])) | {"開始時刻要確認"})
for r in results:
    m = matches[r["match_id"]]
    if r["status"] == "final" and r.get("winner") in ("L", "D", "R"):
        m["status"] = "final"
        m["result"] = dict(winner=r["winner"], score=r["score"], source_rank=r["source_rank"], source_url=r["source_url"],
                           identity_checked=bool(r.get("identity_checked")), identity_note=r.get("identity_note"),
                           note=r.get("note"), checked_at=LOCKED, run_id=RUN_ID)
    elif r["status"] in ("postponed", "cancelled", "abandoned", "live", "unknown") and m["status"] != "final":
        m["status"] = r["status"]
        m["note"] = (m.get("note") or "") + f"／{LOCKED[5:16]}時点 {r['status']}：{(r.get('note') or '')[:240]}"
for lg, L in ledgers.items():
    for e in L:
        if e.get("result"):
            continue
        s = core.settle_entry(e, matches[e["match_id"]])
        if s:
            e["result"] = dict(s, settled_at=LOCKED, run_id=RUN_ID)
            settled_log.append((lg, e["entry_id"], e["selection"], e["odds_taken"], s["outcome"], s.get("profit"),
                                matches[e["match_id"]]["result"]["score"] if matches[e["match_id"]].get("result") else ""))

# 敗戦カードの post-match review（1敗でモデル係数は変えない）
os.makedirs(core.path("reviews"), exist_ok=True)
for lg, eid, sel, o, out, pf, sc in settled_log:
    if out != "loss":
        continue
    e = next(x for x in ledgers[lg] if x["entry_id"] == eid)
    m = matches[e["match_id"]]
    txt = f"""# post-match review: {eid}

- 試合：{m['sport']}／{m['competition']}／{m['start_jst']}／{m['left']} vs {m['right']}
- 採用：{lg} {sel} @ {o}（$100、locked_at {e['locked_at']}、{e['odds_source']}）
- 事前仮説：{e.get('rationale')}（事前推定勝率 {e.get('prior_prob')}）
- 実際の結果：{sc}（{m['result']['source_url']}）
- 見落とし：試合前の情報からは確認できていない（深掘り時点で主力欠場・ローテーション等の記載なし）。試合後情報は事前分析に使わない。
- failure factor：本命側の敗戦。事前推定 {e.get('prior_prob')} に対し負ける確率は約{(1-(e.get('prior_prob') or 0))*100:.0f}%あった。
- variance か structural か：現時点では variance と判定（1敗のみ。同種の敗戦が複数そろった時点で①の格差基準・競技別の較正を再検討する）。
- CLV：終値オッズ未取得のため算出不可。
- 再発防止仮説：①の同競技・同価格帯の成績を積み上げ、的中率が推定勝率を有意に下回る場合に基準を見直す。1敗だけではモデル係数を変更しない。
- 記録：{RUN_ID}（{LOCKED}）
"""
    open(core.path("reviews", f"{eid}.md"), "w", encoding="utf-8").write(txt)

# ================= 2. インベントリ取り込み =================
def clean(n):
    return re.sub(r"\s*\(\d+\)\s*$", "", str(n)).strip()

def norm(n):
    return re.sub(r"[^a-z]", "", clean(n).lower())

fid2mid, fid_swapped, feed_rows, dup = {}, {}, {}, []
seen = {}
MANUAL_DUP = {"bov:31497003": "bov:31424438"}   # LoL WSCI T1 Academy vs Cupid の別行（15:15表記）。同一試合
for x in feed:
    if x["fid"] in MANUAL_DUP:
        dup.append((x["fid"], MANUAL_DUP[x["fid"]])); continue
    key = (x["sport"], x["start_jst"][:10], frozenset((norm(x["left"]), norm(x["right"]))))
    mp = mapping.get(x["fid"])
    if key in seen and not mp:
        dup.append((x["fid"], seen[key])); continue
    if mp:
        mid = mp["match_id"]; fid_swapped[x["fid"]] = bool(mp.get("swapped"))
    else:
        mid = x["new_id"]
    seen[key] = x["fid"]
    fid2mid[x["fid"]] = mid
    feed_rows[mid] = x
    if mid in matches:
        m = matches[mid]
        m.setdefault("feed_ids", [])
        if x["fid"] not in m["feed_ids"]:
            m["feed_ids"].append(x["fid"])
    else:
        team = x["sport"] not in ("テニス", "ダーツ", "スヌーカー", "バドミントン")
        matches[mid] = dict(sport=x["sport"], competition=x["league"], round=None, start_jst=x["start_jst"],
                            left=clean(x["left"]), right=clean(x["right"]),
                            home_away="左＝ホーム（配信表記）" if team else "中立（大会会場）", status="scheduled", result=None,
                            note=f"{x['src']} {x['fid']}（{x['taken_at'][11:16]}取得）", flags=[], feed_ids=[x["fid"]])
    if x["prices"]:
        p = dict(x["prices"])
        if fid_swapped.get(x["fid"]):
            p["L"], p["R"] = p["R"], p["L"]
        via = "Bovada 公開coupon JSON" if x["src"] == "Bovada" else "tennisexplorer経由（ブック別オッズ）"
        odds.append(dict(match_id=mid, taken_at=x["taken_at"], source=f"{x['book']}（{via}・{x['taken_at'][11:16]}取得・{x['fid']}）",
                         market=x["market"], prices=p, exact=True, book_verified=False))


def swap_facts(f):
    f = copy.deepcopy(f)
    f["left"], f["right"] = f.get("right"), f.get("left")
    for h in f.get("h2h") or []:
        h["winner"] = {"left": "right", "right": "left"}.get(h.get("winner"), h.get("winner"))
        h["units_left"], h["units_right"] = h.get("units_right"), h.get("units_left")
        h["score"] = re.sub(r"^(\d+)\s*-\s*(\d+)", lambda mm: f"{mm[2]}-{mm[1]}", str(h.get("score") or ""))
    u = f.get("unavailable") or {}
    if isinstance(u, dict):
        f["unavailable"] = {k.replace("left.", "@@").replace("right.", "left.").replace("@@", "right."): v for k, v in u.items()}
    return f


# 対戦相手が確定した「勝者」表記の既存行（配信で確定）を実名に更新
for mid, side, nm in (("m20260928-2f77907f", "right", "フルカチュ"), ("m20260928-4ef3a3ec", "left", "メドベージェフ"),
                      ("m20260928-4ef3a3ec", "right", "サフィウリン")):
    m = matches[mid]
    if "勝者" in m[side]:
        m["note"] = (m.get("note") or "") + f"／対戦相手確定：{m[side]}→{nm}（tennisexplorer {LOCKED[5:16]}確認）"
        m[side] = nm
    m["flags"] = sorted(set(m.get("flags", [])) - {"対戦相手未確定"})

# 深掘り（fid → match_id）
DD_BY_MID = {}
for fid, x in dd.items():
    mid = fid2mid.get(fid)
    if not mid:
        continue       # 重複fid（同一試合の別行）
    x = copy.deepcopy(x)
    if fid_swapped.get(fid):
        x["facts"] = swap_facts(x["facts"])
        mp_ = x.get("model_prob") or {}
        if mp_.get("prob") is not None:
            mp_["side"] = "R" if mp_.get("side") == "L" else "L"
        if mp_.get("p3"):
            mp_["p3"] = dict(L=mp_["p3"].get("R"), D=mp_["p3"].get("D"), R=mp_["p3"].get("L"))
    if matches[mid]["sport"] == "バスケットボール":
        x["flags"] = [f for f in x.get("flags", []) if f != "短期戦フォーマット"]   # シリーズ形式は1試合の短期戦ではない
    x["facts"]["match_id"] = mid
    x["facts"]["data_as_of"] = x["data_as_of"]
    DD_BY_MID[mid] = x
    matches[mid]["flags"] = sorted(set(matches[mid].get("flags", [])) | set(x.get("flags", [])))
    st = x.get("start_jst_confirmed")
    if isinstance(st, str) and st != matches[mid]["start_jst"] and core.parse(st) > core.parse(LOCKED):
        matches[mid]["note"] = (matches[mid].get("note") or "") + f"／深掘りで開始時刻{st[5:16]}を確認（配信{matches[mid]['start_jst'][5:16]}）"
    core.save(f"facts/{mid}.json", x["facts"])

inventory = sorted([mid for mid, m in matches.items() if m["start_jst"] > LOCKED and m["status"] in ("scheduled", "unknown")],
                   key=lambda k: matches[k]["start_jst"])
HARD = {"ショーマッチ", "下位リーグ（整合性リスク）", "価格が実力差と不整合", "価格が実力差と不整合の可能性", "消化試合",
        "主力休養リスク", "親善試合（ローテーション）", "高地開催の可能性", "BO1", "短期戦フォーマット", "プレシーズン/カップ戦",
        "控え中心の編成", "開始時刻要確認", "対戦相手未確定", "シミュレーション/バーチャル（実力データなし）", "バトルロイヤル（1対1の勝敗市場なし）"}
ESPORTS = {"CS2", "VALORANT", "Dota 2", "LoL", "Rainbow Six", "King of Glory", "Mobile Legends", "StarCraft II", "Call of Duty",
           "Rocket League", "Overwatch 2", "eスポーツ（その他）"}


def cur_prices(mid):
    x = feed_rows.get(mid)
    if not x or not x["prices"]:
        return None
    p = dict(x["prices"])
    if fid_swapped.get(x["fid"]):
        p["L"], p["R"] = p["R"], p["L"]
    return p


def the_model(mid):
    x = DD_BY_MID[mid]
    if matches[mid]["sport"] in ESPORTS:
        md, why = model.log5(x["facts"])
        if md:
            md["p"] = {"L": md["prob"], "R": 1 - md["prob"]}
            md["internal"] = True
        return md, why
    mp = x.get("model_prob") or {}
    if matches[mid]["sport"] == "サッカー":
        p3 = mp.get("p3")
        if not p3 or any(p3.get(k) is None for k in ("L", "D", "R")):
            return None, (mp.get("reason") or "独立モデルなし") + "（1X2には3択の独立モデルが必要）"   # 1X2 は引分け確率が必要
        tot = sum(p3[k] for k in ("L", "D", "R"))
        pp = {k: p3[k] / tot for k in ("L", "D", "R")}
        return dict(prob=pp["L"], side="L", method=mp.get("method", ""), inputs=f"as_of {mp.get('as_of')}（{mp.get('url','')}）・3択を合計1に正規化",
                    p=pp, internal=False, opaque=True), None
    if mp.get("prob") is None:
        return None, (mp.get("reason") or "独立モデルなし")
    if "eloratings" in (mp.get("method") or ""):
        return None, "eloratings.netの勝率は引分け0.5換算のため使わない"
    p = mp["prob"] if mp["side"] == "L" else 1 - mp["prob"]
    return dict(prob=p, side="L", method=mp.get("method", ""), inputs=f"as_of {mp.get('as_of')}（{mp.get('url','')}）",
                p={"L": p, "R": 1 - p}, internal=False), None


def summ(v, why):
    if v is None or v == "" or v == [] or (isinstance(v, dict) and v.get("unavailable")):
        return UA(v.get("reason") if isinstance(v, dict) and v.get("reason") else why)
    if isinstance(v, list):
        return "／".join(map(str, v))
    return v


def detail(mid, ext):
    x = DD_BY_MID[mid]; m = matches[mid]; fr = feed_rows[mid]; sm = x.get("summary") or {}
    p = cur_prices(mid)
    ext_mk = UA("Bovada以外のブックの比較値なし（公開配信は1社のみ）")
    if fr.get("books"):
        bk = fr["books"]
        sw = fid_swapped.get(fr["fid"])
        ext_mk = "／".join(f"{b} {v[1] if sw else v[0]}-{v[0] if sw else v[1]}" for b, v in list(bk.items())[:8])
    d = dict(title=m["sport"], competition=m["competition"], date=m["start_jst"][:10], start_jst=m["start_jst"],
             matchup=f'{m["left"]} vs {m["right"]}',
             ranking=summ(sm.get("ranking"), "順位情報なし"), h2h=summ(sm.get("h2h"), "過去の対戦が見つからない"),
             recent_form=summ(sm.get("recent_form"), "直近成績なし"), venue=summ(sm.get("venue"), "会場情報なし"),
             lineup=summ(sm.get("lineup"), "メンバー情報なし"),
             odds=dict(book=fr["book"], via=fr["src"], fid=fr["fid"], taken_at=fr["taken_at"], market=fr["market"], exact=True, **p),
             odds_exact=True, external_market=ext_mk,
             risks=summ(x.get("risks"), "リスク記載なし"), missing=summ(x.get("missing"), "不足なし"),
             source_urls=x.get("source_urls") or UA("出典なし"), data_as_of=x["data_as_of"],
             start_confirmed=x.get("start_jst_confirmed"))
    if m["sport"] in ESPORTS:
        es = x.get("esports") or {}
        for k in ("format", "lan_online", "roster", "map_pool", "veto", "patch", "series_h2h", "map_h2h", "rating"):
            d[k] = summ(es.get(k), "取得できず")
    d.update(ext)
    for k in ("required_prob", "prior_prob", "edge_or_ev", "rationale"):
        d.setdefault(k, UA("算出不可"))
    return d


def entry(lg, mid, side, o, prior, why):
    m = matches[mid]; fr = feed_rows[mid]
    return dict(entry_id=f"{lg}-{mid}-{side}", match_id=mid, market=fr["market"],
                selection=m["left"] if side == "L" else m["right"], selection_key=side, stake=core.STAKE,
                odds_taken=o, locked_at=LOCKED, odds_source=f"{fr['book']}（{fr['src']}・{fr['taken_at'][11:16]}取得・{fr['fid']}）",
                prior_prob=round(prior, 4), rationale=why, result=None)


rows = {lg: [] for lg in core.LOGICS}
new_entries = {lg: [] for lg in core.LOGICS}
for mid in inventory:
    m = matches[mid]
    p = cur_prices(mid)
    prevs = {lg: ana_prev[lg].get(mid) for lg in core.LOGICS}
    deep = mid in DD_BY_MID and core.parse(m["start_jst"]) > core.parse(LOCKED)
    if not deep and prevs["r1"] and prevs["r1"].get("deep_dive"):
        for lg in core.LOGICS:
            r = copy.deepcopy(prevs[lg])
            tag = "（前回の深掘り判定を引継ぎ）"
            if tag not in str(r.get("reason")):
                r["reason"] = str(r.get("reason")) + tag
            if p and lg == "r1":
                r["current_odds"] = p
            rows[lg].append(r)
        continue
    if not p:
        for lg in core.LOGICS:
            if prevs[lg]:
                r = copy.deepcopy(prevs[lg])
                r["reason"] = str(r.get("reason")) + "（今回の公開配信に掲載なし・前回判定を引継ぎ）" if "前回判定を引継ぎ" not in str(r.get("reason")) else r["reason"]
            else:
                r = dict(match_id=mid, status="nodata", reason="公開配信（Bovada/tennisexplorer）に価格なし", deep_dive=False, priced=False)
            rows[lg].append(r)
        continue
    flags = set(m.get("flags", []))
    hard = sorted(flags & HARD)
    name = lambda k: m["left"] if k == "L" else m["right"] if k == "R" else "引分け"
    nv, over = core.no_vig(p)
    fav = min(("L", "R"), key=lambda s: p[s]); fo = p[fav]; gap = round(nv[fav] * 100)
    within = core.parse(m["start_jst"]).timestamp() <= H24
    md, mwhy = the_model(mid) if deep else (None, "深掘り未実施")
    for lg in core.LOGICS:
        r = dict(match_id=mid, deep_dive=deep, priced=True)
        if not deep:
            lack = "開始まで24時間超：直前の定時更新で深掘りしてから判定する" if not within else "深掘り未実施（競技内の深掘り枠外）"
            if lg == "r1":
                r.update(pick=name(fav), odds=fo, gap=gap, nv=round(nv[fav]*100, 1), overround=round(over*100, 1))
                if fo < 1.05: r.update(status="rejected", reason=f"リターン過小（{fo}）")
                elif fo > 1.45: r.update(status="rejected", reason=f"格差不足（本命{fo}・適正勝率{nv[fav]*100:.0f}%）")
                elif gap >= 70: r.update(status="watch", reason=f"一次通過（格差{gap}）・{lack}")
                else: r.update(status="rejected", reason=f"格差{gap}（基準70未満・本命{fo}）")
            elif lg == "r2":
                r.update(status="excluded", pick=name(fav), odds=fo, need=round(100/fo, 1),
                         reason=f"独立勝率なし：{lack}（必要勝率{100/fo:.1f}%のみ算出）")
            elif lg == "r3":
                cand = [s for s in ("L", "R") if 1.50 <= p[s] <= 3.00]
                if not cand:
                    r.update(status="excluded", pick=name(fav), odds=fo, reason=f"対象価格帯（1.50〜3.00）の選択肢なし（本命{fo}）")
                else:
                    k = max(cand, key=lambda s: p[s])
                    r.update(status="excluded", pick=name(k), odds=p[k], need=round(100/p[k], 1),
                             reason=f"市場差を測る独立推定なし：{lack}（市場ベースライン{nv[k]*100:.1f}%）")
            else:
                r.update(status="rejected", pick=name(fav), odds=fo, fair=round(nv[fav]*100, 1), reliability="low",
                         reason=f"独立ベース確率なし：{lack}（市場確率の流用は禁止）")
            rows[lg].append(r); continue
        # ---------- 深掘りあり：ロジック別に独立判定 ----------
        mname = (md or {}).get("method", "")
        if lg == "r1":
            r.update(pick=name(fav), odds=fo, nv=round(nv[fav]*100, 1), gap=gap, overround=round(over*100, 1))
            ext = dict(required_prob=round(1/fo, 4), prior_prob=round(nv[fav], 4), edge_or_ev=f"格差{gap}",
                       rationale=f"①：{name(fav)} {fo}（{feed_rows[mid]['book']}）。控除後の適正勝率{nv[fav]*100:.1f}%。" + (f"リスク：{'・'.join(hard)}" if hard else "重大なリスク要因なし"))
            if fo < 1.05: r.update(status="rejected", reason=f"リターン過小（{fo}）")
            elif fo > 1.45: r.update(status="rejected", reason=f"格差不足（本命{fo}）")
            elif hard: r.update(status="watch", reason="深掘り済み・リスク要因：" + "・".join(hard))
            elif gap >= 70:
                r.update(status="accepted", reason=f"格差{gap}・{feed_rows[mid]['book']} {fo}で正式採用")
                new_entries[lg].append(entry(lg, mid, fav, fo, nv[fav], ext["rationale"]))
            elif gap >= 63: r.update(status="watch", reason=f"格差{gap}（基準70未満）")
            else: r.update(status="rejected", reason=f"格差{gap}")
        elif lg == "r2":
            if not md:
                r.update(status="excluded", pick=name(fav), odds=fo, need=round(100/fo, 1), reason=f"独立モデルなし：{mwhy}")
                ext = dict(required_prob=round(1/fo, 4), prior_prob=UA(mwhy), edge_or_ev=UA(mwhy), rationale="②：" + mwhy)
            else:
                W = 0.08 if md["internal"] else 0.04
                best = max([s for s in md["p"] if s in p], key=lambda s: md["p"][s]*p[s]); o = p[best]; q = md["p"][best]
                evm, evl, evh = q*o-1, (q-W)*o-1, (q+W)*o-1
                r.update(pick=name(best), odds=o, need=round(100/o, 1), est=f"{(q-W)*100:.1f}〜{(q+W)*100:.1f}%",
                         ev_range=f"{evl*100:+.1f}〜{evh*100:+.1f}%")
                ext = dict(required_prob=round(1/o, 4), prior_prob=round(q, 4), edge_or_ev=f"EV{evm*100:+.1f}%",
                           rationale=f"②：{mname[:50]}。{md.get('inputs','')[:80]}。{name(best)}勝率{q:.3f}を±{W}で評価、必要勝率{1/o:.3f}。")
                gapm = abs(q - nv[best]) * 100
                if gapm > DIV:
                    r.update(status="watch", reason=f"モデルと市場の乖離{gapm:.0f}pt（{DIV}pt超は情報不足・モデル歪みの可能性があり正式採用しない）・中央EV{evm*100:+.1f}%")
                elif evl >= 0 and evm >= 0.02 and not hard:
                    r.update(status="formal", reason=f"レンジ下限でもEV{evl*100:+.1f}%")
                    new_entries[lg].append(entry(lg, mid, best, o, q, ext["rationale"]))
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
                ext = dict(required_prob=round(1/fo, 4), prior_prob=UA("価格帯外"), edge_or_ev=UA("価格帯外"), rationale="③：価格帯外（1.50〜3.00の選択肢なし）")
            elif not md:
                k = cand[0]
                r.update(status="excluded", pick=name(k), odds=p[k], need=round(100/p[k], 1), reason=f"独立推定なし：{mwhy}")
                ext = dict(required_prob=round(1/p[k], 4), prior_prob=UA(mwhy), edge_or_ev=UA(mwhy), rationale=f"③：市場ベースライン{nv[k]*100:.1f}%との差を測る独立推定なし（{mwhy}）")
            else:
                k = max(cand, key=lambda s: md["p"][s] - nv[s]); o = p[k]
                diff = (md["p"][k] - nv[k]) * 100; ev_ = md["p"][k]*o - 1
                risk = "高" if hard else "中" if o < 1.8 else "中〜高" if o < 2.4 else "高"
                r.update(pick=name(k), odds=o, need=round(100/o, 1), est=f"{md['p'][k]*100:.1f}%", diff=f"{diff:+.1f}pt", upset=risk)
                ext = dict(required_prob=round(1/o, 4), prior_prob=round(md["p"][k], 4), edge_or_ev=f"市場差{diff:+.1f}pt／EV{ev_*100:+.1f}%",
                           rationale=f"③：市場ベースライン{nv[k]*100:.1f}%に対し{mname[:30]}は{md['p'][k]*100:.1f}%。Upset Risk {risk}。")
                if abs(diff) > DIV:
                    r.update(status="watch" if diff > 0 else "excluded", reason=f"市場差{diff:+.1f}pt（{DIV}pt超はモデル歪みの可能性があり正式採用しない）")
                elif diff >= 3 and ev_ >= 0.02 and risk != "高":
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
                ext = dict(required_prob=round(1/fo, 4), prior_prob=UA(mwhy), edge_or_ev=UA(mwhy), rationale="④：base_probability なし（" + mwhy + "）")
            else:
                fin = {s: 0.5*nv[s] + 0.5*md["p"][s] for s in md["p"] if s in p}
                k = max(fin, key=lambda s: fin[s]*p[s]); o = p[k]
                edge = (fin[k] - nv[k]) * 100; ev_ = fin[k]*o - 1
                rel = "low" if hard else ("medium" if md["internal"] or md.get("opaque") or feed_rows[mid]["book"] == "Bovada" else "high")
                r.update(pick=name(k), odds=o, fair=round(nv[k]*100, 1), final=round(fin[k]*100, 1), edge=f"{edge:+.1f}pt",
                         ev=f"{ev_*100:+.1f}%", min_odds=math.ceil(100/fin[k])/100, reliability=rel,
                         base_prob=round(md["p"][k], 4), market_prob=round(nv[k], 4))
                ext = dict(required_prob=round(1/o, 4), prior_prob=round(fin[k], 4), edge_or_ev=f"EDGE{edge:+.1f}pt／EV{ev_*100:+.1f}%",
                           rationale=f"④：market {nv[k]:.3f}（no-vig）＋base {md['p'][k]:.3f}（{mname[:25]}）を等分、expert_adjustment 0 → final {fin[k]:.3f}。")
                if abs(md["p"][k] - nv[k]) * 100 > DIV:
                    r.update(status="watch" if edge >= 1.5 else "rejected", reason=f"baseと市場の乖離{abs(md['p'][k]-nv[k])*100:.0f}pt：{DIV}pt超は正式採用しない（EDGE{edge:+.1f}pt・EV{ev_*100:+.1f}%）")
                elif edge >= 3 and ev_ >= 0.03 and rel != "low":
                    r.update(status="accepted", reason=f"EDGE{edge:+.1f}pt・EV{ev_*100:+.1f}%")
                    new_entries[lg].append(entry(lg, mid, k, o, fin[k], ext["rationale"]))
                elif edge >= 1.5 and ev_ > -0.01:
                    r.update(status="watch", reason=f"EDGE{edge:+.1f}pt・EV{ev_*100:+.1f}%（基準未達）")
                else:
                    r.update(status="rejected", reason=f"EDGE{edge:+.1f}pt・EV{ev_*100:+.1f}%")
        r["rationale"] = ext["rationale"]
        r["deep_dive_detail"] = detail(mid, ext)
        rows[lg].append(r)

# ================= 3. 保存 =================
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
core.save("ledger/experience.json", ledgers["experience"])
core.save(f"snapshots/{RUN_ID}/inventory.json", dict(taken_at=LOCKED, feed_bovada=feed[0]["taken_at"] if feed else None,
                                                    match_ids=inventory, feed_ids={k: v for k, v in fid2mid.items()}, duplicates_skipped=dup))

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
        lc = coverage[sp].setdefault(lg, dict(screened=0, deep_dive=0, formal=0, watch=0, rejected=0, nodata=0))
        lc["screened"] += 1; lc["deep_dive"] += int(bool(r.get("deep_dive")))
        s = r["status"]
        lc["formal" if s == FORMAL[lg] else "watch" if s in ("watch", "conditional") else "nodata" if s == "nodata" else "rejected"] += 1
for sp, c in coverage.items():
    for lg in core.LOGICS:
        lc = c[lg]
        if c["priced_upcoming_count"] and not lc["deep_dive"]:
            lc["deep_dive_waiver"] = ("今回の公開配信に価格がなく（前回取得値のみ）今回の深掘り対象外" if not c["fresh_priced"]
                                      else "24時間以内の試合がなく、次回以降の定時更新で深掘り" if not c["in_24h"]
                                      else "未実施：本回の深掘り枠に入らず（次回の対象）")
runs = core.load("automation-runs.json")
prev = runs[-1]
gone = {sp: "対象時間内に未開始の試合なし（全試合開始済み・終了）" for sp in prev["coverage"] if sp not in coverage}
json.dump(dict(rows={lg: len(v) for lg, v in rows.items()}, new={lg: [(e["selection"], e["odds_taken"], matches[e["match_id"]]["sport"], e["match_id"]) for e in v] for lg, v in new_entries.items()},
               settled=settled_log, inventory=len(inventory), coverage=coverage, gone=gone, dup=dup),
          open(f"{DD}/run_out.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("inventory", len(inventory), "settled", len(settled_log), "dup", len(dup))
for lg in core.LOGICS:
    print(lg, [(e["selection"], e["odds_taken"], matches[e["match_id"]]["sport"]) for e in new_entries[lg]])
