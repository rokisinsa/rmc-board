"""競技枠：リアルスポーツ・eスポーツの全競技（タイトル）から、①〜④それぞれ必ず正式採用を出す（ユーザー指示 2026-09-29）。
通常の基準で正式採用が1件もない競技は、その競技の中で各ロジックの指標が最も良い1件を「競技枠」として正式採用する。
通常基準を満たすものは今まで通り上限なしで全部採用する（競技枠はその上乗せ）。

競技枠の最低条件（これを満たす試合がない競技からは出さない）：
- 深掘り済み（facts あり・両チームとも公式戦の実績が1試合以上）
- 単一ブックの exact odds（L/R）がある
- 判定時刻より後、かつ24時間以内に始まる
- シミュレーション・ショーマッチ・バトルロイヤル・開始時刻要確認・対戦相手未確定ではない
- ②③④は独立勝率（外部モデル、無ければ rmc/model.py の log5）が出せる試合だけ
- ②③④は、独立勝率と市場（控除後）の差が15pt以内・オッズ4.0以下の候補を優先する（log5の歪みで大穴を拾わないため）。
  その競技に該当がなければ、市場との差が最も小さい候補（いちばん無理のない候補）を出す
"""
DIV = 0.15
MAX_ODDS = 4.0
import json, os
from . import core, model

FLOOR_EXCLUDE = {"シミュレーション/バーチャル（実力データなし）", "ショーマッチ", "バトルロイヤル（1対1の勝敗市場なし）",
                 "開始時刻要確認", "対戦相手未確定"}
TAG = "競技枠"


def _facts(mid):
    p = core.path("facts", f"{mid}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _odds(row):
    o = (row.get("deep_dive_detail") or {}).get("odds") or {}
    if isinstance(o, dict) and _num(o.get("L")) and _num(o.get("R")) and o.get("exact", True):
        return o
    return None


def _model_p(lg, row, fx):
    """左側の独立勝率。ロジックの判定で使った外部モデル値を優先し、無ければ log5。"""
    d = row.get("deep_dive_detail") or {}
    p = None
    if lg in ("r2", "r3") and _num(d.get("prior_prob")) and row.get("pick"):
        p = d["prior_prob"]
    elif lg == "r4" and _num(row.get("base_prob")):
        p = row["base_prob"]
    if p is not None:  # 採用側の勝率 → 左側の勝率に直す
        m_left = row.get("_left")
        return (p if row.get("pick") == m_left else 1 - p), "判定時の独立モデル"
    md, _ = model.log5(fx) if fx else (None, None)
    if md:
        return md["prob"], md["method"]
    return None, None


def eligible(row, match, locked):
    if not row.get("deep_dive") or not _odds(row):
        return False
    st = match.get("start_jst")
    if not st or st <= locked or not core.within_horizon(locked, st):
        return False
    if set(match.get("flags", [])) & FLOOR_EXCLUDE:
        return False
    fx = _facts(row["match_id"])
    if not fx:
        return False
    return bool((fx.get("left") or {}).get("form")) and bool((fx.get("right") or {}).get("form"))


def candidate(lg, row, match):
    """(score, side, odds, prior, why) を返す。出せなければ None。"""
    o = _odds(row)
    prices = {"L": o["L"], "R": o["R"]}
    if _num(o.get("D")):
        prices["D"] = o["D"]
    nv, _ = core.no_vig(prices)
    if lg == "r1":
        k = min(("L", "R"), key=lambda s: prices[s])
        if prices[k] < 1.05:
            return None
        return nv[k], k, prices[k], nv[k], f"控除後勝率{nv[k]*100:.1f}%（格差{round(nv[k]*100)}）が競技内で最上位", 0.0
    row = dict(row, _left=match["left"])
    pL, method = _model_p(lg, row, _facts(row["match_id"]))
    if pL is None:
        return None
    p = {"L": pL, "R": 1 - pL}
    ok = [s for s in ("L", "R") if abs(p[s] - nv[s]) <= DIV and prices[s] <= MAX_ODDS] or ["L", "R"]
    if lg == "r2":
        k = max(ok, key=lambda s: p[s] * prices[s])
        ev = p[k] * prices[k] - 1
        return ev, k, prices[k], p[k], f"独立勝率{p[k]*100:.1f}%（{method[:30]}）×{prices[k]} の中央EV{ev*100:+.1f}%が競技内で最上位", abs(p[k] - nv[k])
    if lg == "r3":
        cand = [s for s in ("L", "R") if 1.50 <= prices[s] <= 3.00]
        if not cand:
            return None
        k = max([c for c in cand if abs(p[c] - nv[c]) <= DIV] or cand, key=lambda s: p[s] - nv[s])
        diff = (p[k] - nv[k]) * 100
        return diff, k, prices[k], p[k], f"市場{nv[k]*100:.1f}%に対し独立勝率{p[k]*100:.1f}%（差{diff:+.1f}pt）が競技内で最上位", abs(p[k] - nv[k])
    fin = {s: 0.5 * nv[s] + 0.5 * p[s] for s in ("L", "R")}
    k = max(ok, key=lambda s: fin[s] * prices[s])
    ev = fin[k] * prices[k] - 1
    return ev, k, prices[k], fin[k], f"市場と独立勝率を等分したfinal {fin[k]*100:.1f}%でEV{ev*100:+.1f}%が競技内で最上位", abs(p[k] - nv[k])


def apply_floor(lg, rows, matches, ledger, locked):
    """rows（その回の判定行）を書き換え、追加すべき ledger エントリのリストを返す。"""
    formal = core.FORMAL[lg]
    by_sport = {}
    for r in rows:
        m = matches.get(r["match_id"]) or {}
        by_sport.setdefault(m.get("sport"), []).append(r)
    new = []
    for sport, rs in by_sport.items():
        live = [r for r in rs if (matches[r["match_id"]].get("start_jst") or "") > locked]
        if any(r.get("status") == formal for r in live):
            continue
        cands = []
        for r in live:
            m = matches[r["match_id"]]
            if eligible(r, m, locked):
                c = candidate(lg, r, m)
                if c:
                    cands.append((c, r, m))
        if not cands:
            continue
        good = [x for x in cands if x[0][5] <= DIV and x[0][2] <= MAX_ODDS]
        if good:
            best = max(good, key=lambda x: x[0][0])
        else:   # ガード内の候補がない競技：市場との差が最も小さい（無理のない）候補
            best = min(cands, key=lambda x: x[0][5])
            best = ((best[0][0], best[0][1], best[0][2], best[0][3], best[0][4] + "（市場との差が大きい候補しかなく、差が最小のものを選択）", best[0][5]), best[1], best[2])
        (score, side, odds, prior, why, _div), r, m = best
        eid = core.next_entry_id(ledger + new, lg, r["match_id"], side)
        if eid is None:
            continue
        o = _odds(r)
        prev = f"{r.get('status')}：{r.get('reason')}"
        r["status"] = formal
        r["pick"] = m["left"] if side == "L" else m["right"]
        r["odds"] = odds
        r["reason"] = f"{TAG}（{sport}の中で最上位・全競技から必ず出す）：{why}。通常基準での判定は {prev}"
        r["pick_type"] = "sport_floor"
        src = f"{o.get('book', '不明')}（{o.get('via', '')}・{str(o.get('taken_at', ''))[11:16]}取得・{o.get('fid') or o.get('betchannel_event_id') or ''}）"
        new.append(dict(entry_id=eid, match_id=r["match_id"], market=o.get("market", "MatchWinner"),
                        selection=r["pick"], selection_key=side, stake=core.STAKE, odds_taken=odds, locked_at=locked,
                        odds_source=src, prior_prob=round(prior, 4), rationale=r["reason"], pick_type="sport_floor", result=None))
    return new


def missing_floor(lg, rows, matches, locked):
    """競技枠の対象になるのに正式採用が1件もない競技（validate 用）。"""
    formal = core.FORMAL[lg]
    by_sport = {}
    for r in rows:
        m = matches.get(r["match_id"]) or {}
        by_sport.setdefault(m.get("sport"), []).append(r)
    out = []
    for sport, rs in by_sport.items():
        live = [r for r in rs if (matches[r["match_id"]].get("start_jst") or "") > locked]
        if any(r.get("status") == formal for r in live):
            continue
        if any(eligible(r, matches[r["match_id"]], locked) and candidate(lg, r, matches[r["match_id"]]) for r in live):
            out.append(sport)
    return out
