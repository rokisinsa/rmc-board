"""06:00枠（10-02）：⑤一次候補の facts に、手元データ（LiveScore順位表・結果、tennisexplorer、既存facts）から機械的に出せる
deep5 項目（順位・H2H・H2H得失点・会場別H2H・60日共通相手）と、データで判定できる反対材料（古いH2H・ホーム/アウェー差・最近の急改善・
BO1・LAN/Online差＝非eスポーツ）を書く。Web調査が必要な項目（欠場・ロスター・ローテーション・世代交代・消化試合）はサブエージェントが追記。
既に値がある項目は上書きしない。数字は作らない。使い方: python scripts/run_20261002_0600_prefill.py [tier...]"""
import json, os, sys, re, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core, discover as D
from rmc.facts import _norm
tiers = {int(x) for x in sys.argv[1:]} or {1, 2, 3}
m = core.load("matches.json")
scr = core.load("discovery/latest.json")
ls = D._ls()
NONSPORT_ES = "非eスポーツ"
n = 0
for r in scr["rows"]:
    if r.get("status") not in ("一次候補", "深掘り未完") or r.get("tier") not in tiers:
        continue
    mid = r["match_id"]; mm = m.get(mid)
    fx = D._facts(mid)
    if not mm or not fx:
        continue
    sport = mm["sport"]; es = sport in D.ESPORTS
    dd = fx.setdefault("deep5", {}); un = fx.setdefault("unavailable", {}); ce = fx.setdefault("counter_evidence", {})
    L, R = mm["left"], mm["right"]
    votes = {"L": 0, "R": 0}
    for h in r.get("hits") or []:
        votes[h["side"]] += 1
    fav = "L" if votes["L"] >= votes["R"] else "R"
    dog = "R" if fav == "L" else "L"
    nm = {"L": L, "R": R}; sd = {"L": "left", "R": "right"}
    lf, flip = D.ls_fixture(mm) if sport in ("サッカー", "アイスホッケー", "バスケットボール", "クリケット") else (None, None)
    stg = (ls["stages"].get(lf["stage"]) or {}) if lf else {}
    tl, tr = ((lf["t2"], lf["t1"]) if flip else (lf["t1"], lf["t2"])) if lf else (None, None)
    # ---- ranking ----
    if not dd.get("ranking"):
        tb = stg.get("table") or {}
        if tl in tb and tr in tb:
            a, b = tb[tl], tb[tr]
            dd["ranking"] = (f"{L} {a.get('rank')}位（{a.get('played')}試合 勝点{a.get('pts')}・{a.get('W')}勝{a.get('D') or 0}分{a.get('L')}敗 得失{a.get('gf')}-{a.get('ga')}）／"
                             f"{R} {b.get('rank')}位（{b.get('played')}試合 勝点{b.get('pts')}・{b.get('W')}勝{b.get('D') or 0}分{b.get('L')}敗 得失{b.get('gf')}-{b.get('ga')}）"
                             f"（LiveScore順位表 {stg.get('name')}・{ls['taken_at']}取得）")
        else:
            mt = fx.get("metrics") or {}
            rl, rr = (mt.get("left") or {}).get("rank"), (mt.get("right") or {}).get("rank")
            if rl or rr:
                dd["ranking"] = f"{L} {'世界' + str(rl) + '位' if rl else '順位なし'}／{R} {'世界' + str(rr) + '位' if rr else '順位なし'}（{mt.get('source') or '自動取得'}）"
    # ---- H2H ----
    h2h = fx.get("h2h") or []
    if not dd.get("h2h_all"):
        if h2h:
            dd["h2h_all"] = f"{len(h2h)}件：" + "／".join(f"{g.get('date')} {g.get('event') or ''} {g.get('score')}（{'左' if g.get('winner') == 'left' else '右' if g.get('winner') == 'right' else '引分'}）" for g in h2h[:10]) + \
                            f"（出典：{(fx.get('source_urls') or ['自動取得'])[0]}。自動取得元の収録範囲内）"
        else:
            dd["h2h_all"] = f"自動取得元（{'LiveScore今季ステージ結果' if lf else 'tennisexplorer' if sport == 'テニス' else '既存facts'}）で直接対戦の記録なし"
    if not dd.get("h2h_points"):
        if h2h:
            def u(g, i):
                if g.get("units_left") is not None and g.get("units_right") is not None:
                    return (g["units_left"], g["units_right"])[i]
                mm_ = re.match(r"^\s*(\d+)\s*-\s*(\d+)", str(g.get("score") or ""))
                return int(mm_[i + 1]) if mm_ else 0
            a = sum(u(g, 0) for g in h2h); b = sum(u(g, 1) for g in h2h)
            dd["h2h_points"] = f"H2H合計 {L} {a}-{b} {R}（{len(h2h)}件・{'セット' if sport == 'テニス' else '得点'}）"
        else:
            dd["h2h_points"] = "直接対戦の記録なし（H2H得失点は算出対象なし）"
    if not dd.get("h2h_home_away"):
        if sport in ("テニス", "ダーツ", "スヌーカー", "バドミントン") or es:
            dd["h2h_home_away"] = "中立会場の競技（ホーム/アウェーの区別なし）"
        elif h2h and stg:
            parts = []
            for rr_ in stg.get("results") or []:
                if {rr_["t1"], rr_["t2"]} == {tl, tr}:
                    parts.append(f"{rr_['date']} {rr_['t1']}（ホーム）{rr_['s1']}-{rr_['s2']} {rr_['t2']}")
            dd["h2h_home_away"] = "／".join(parts) if parts else "会場別のH2Hデータなし"
        elif h2h:
            dd["h2h_home_away"] = "H2Hの会場（ホーム/アウェー）情報が自動取得元にない"
        else:
            dd["h2h_home_away"] = "直接対戦の記録なし（会場別H2Hなし）"
    # ---- 60日共通相手 ----
    if not dd.get("common_60d"):
        try:
            d0 = core.parse(mm["start_jst"]).date()
        except Exception:
            d0 = None
        def games(side):
            out = {}
            for g in ((fx.get(side) or {}).get("form") or []) + ((fx.get(side) or {}).get("history") or []):
                ds = str(g.get("date") or "")
                try:
                    gd = dt.date.fromisoformat(ds[:10])
                except Exception:
                    continue
                if d0 and 0 <= (d0 - gd).days <= 60 and g.get("opp"):
                    out.setdefault(_norm(g["opp"]), []).append(f"{g['opp']} {g.get('score')}{g.get('res')}（{ds[:10]}）")
            return out
        gl, gr = games("left"), games("right")
        com = [k for k in gl if k in gr and k not in (_norm(L), _norm(R))]
        dd["common_60d"] = (f"60日以内の共通相手{len(com)}：" + "／".join(f"左 {'・'.join(gl[k])} ／ 右 {'・'.join(gr[k])}" for k in com[:6])
                            if com else "両者の直近成績（60日以内）に共通の対戦相手なし")
    # ---- 先制率等：自動取得元に得点順・セット順のデータがない ----
    if not dd.get("first_rate") and not any("first_rate" in k or "先制率" in k for k in un):
        if sport == "テニス":
            fs = []
            for side, lab in (("left", L), ("right", R)):
                rows = [g for g in (fx.get(side) or {}).get("form") or [] if g.get("detail")]
                w = 0; k_ = 0
                for g in rows[:10]:
                    s1 = re.match(r"^\s*(\d+)-(\d+)", g["detail"])
                    if s1:
                        k_ += 1; a_, b_ = int(s1[1]), int(s1[2])
                        # detail は勝者側から書かれる（tennisexplorer）：勝った試合は自分側先、負けは相手側先
                        mine = (a_ > b_) if g["res"] == "W" else (b_ > a_)
                        w += mine
                if k_:
                    fs.append(f"{lab} 第1セット取得 {w}/{k_}（直近{k_}試合）")
            if len(fs) == 2:
                dd["first_rate"] = "／".join(fs) + "（tennisexplorerのスコア詳細から）"
        if not dd.get("first_rate"):
            un["first_rate"] = "先制率/第1セット/Map1: 自動取得元（LiveScore・tennisexplorer一覧）は最終スコアのみで得点順・ピリオド別の記録がなく、Tier1の検索予算（1試合5回目安）内で取得できる公開統計もない"
    for k in D.DEEP_EXTRA.get(sport, ()):
        if not dd.get(k) and k not in un:
            un[k] = f"{D.DEEP_LABEL[k]}: 自動取得元（LiveScore）に個人・特殊チーム統計がない。下位リーグは公開統計が乏しく、深掘りで確認できた分だけ deep5 に記録"
    # ---- データで判定できる反対材料 ----
    def put(k, finding, impact, applies):
        if k not in ce or D.UNCHECKED.search(str((ce.get(k) or {}).get("finding") or "")):
            ce[k] = dict(finding=finding, impact=impact, applies=applies)
    if not es:
        put("BO1", f"{sport}は1試合で決着する通常形式（eスポーツのBO1/BO3の区別は該当しない）" if sport != "テニス" else "テニスの3セットマッチ（BO1形式ではない）", "none", False)
        put("LAN/Online差", f"{sport}は対面の通常開催（LAN/Onlineの区別は該当しない）", "none", False)
    if h2h:
        yrs = sorted(str(g.get("date"))[:4] for g in h2h)
        old = yrs[0] < "2024"
        uses = any(h.get("group") == "h2h" for h in r.get("hits") or [])
        put("古いH2H", f"H2H {len(h2h)}件（最古{yrs[0]}・最新{yrs[-1]}）。" + ("格差判定にH2Hを使っており、古い対戦が含まれる" if old and uses else "格差判定はH2Hの古さに依存しない"),
            "minor" if old and uses else "none", bool(old and uses))
    else:
        put("古いH2H", "直接対戦の記録なし（自動取得元の範囲）。格差判定はH2Hに依存していない", "none", False)
    # ホーム/アウェー差
    if sport in ("テニス", "ダーツ", "スヌーカー", "バドミントン") or es:
        put("ホーム/アウェー差", "中立会場の競技（大会会場）でホーム/アウェー差なし", "none", False)
    else:
        ha_txt = str(mm.get("home_away") or "")
        if mid.startswith(("ls-", "ex-")) and lf:
            fav_home = (fav == "L") != bool(flip)
        elif "右＝ホーム" in ha_txt:
            fav_home = fav == "R"
        elif "左＝ホーム" in ha_txt:
            fav_home = fav == "L"
        else:
            fav_home = None
        if fav_home is None:
            put("ホーム/アウェー差", "会場（どちらのホームか）が自動取得元で確定できず、ホーム/アウェー差は評価できない", "minor", True)
        else:
            want = "H" if fav_home else "A"
            rows = [g for g in (fx.get(sd[fav]) or {}).get("form") or [] if g.get("ha") == want]
            w = sum(1 for g in rows if g.get("res") == "W"); l_ = sum(1 for g in rows if g.get("res") == "L")
            bad = (not fav_home) and len(rows) >= 3 and w <= l_
            put("ホーム/アウェー差", f"格差上位側（{nm[fav]}）は{'ホーム' if fav_home else 'アウェー'}。直近の{'ホーム' if fav_home else 'アウェー'}成績 {w}勝{len(rows) - w - l_}分{l_}敗（{len(rows)}試合）" +
                ("：アウェーで勝ち越せておらず不確実性あり" if bad else ""), "minor" if bad else "none", bool(bad))
    # 最近の急改善（格差下位側の直近3試合）
    drows = [g for g in (fx.get(sd[dog]) or {}).get("form") or [] if g.get("res") in ("W", "L", "D")][:3]
    if len(drows) >= 3:
        w = sum(1 for g in drows if g["res"] == "W")
        put("最近の急改善", f"格差下位側（{nm[dog]}）の直近3試合 " + "・".join(f"{g.get('date')} {g.get('score')}{g['res']}" for g in drows) +
            ("：直近で勝ちが続き改善傾向" if w >= 2 else "：急改善の兆候なし"), "minor" if w >= 2 else "none", w >= 2)
    with open(core.path("facts", f"{mid}.json"), "w", encoding="utf-8") as fh:
        json.dump(fx, fh, ensure_ascii=False, indent=1); fh.write("\n")
    n += 1
print("prefilled", n)
