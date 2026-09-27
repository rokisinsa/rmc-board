"""RMC 共通処理：読み書き・no-vig・精算・収支集計。標準ライブラリのみ。"""
import json, math, os, re
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
JST = timezone(timedelta(hours=9))
LOGICS = ("r1", "r2", "r3", "r4")
LOGIC_TITLES = {"r1": "① 推奨取引", "r2": "② VALUE①", "r3": "③ VALUE②", "r4": "④ PRO EDGE"}
# 各ロジックの判定語彙（チェックリスト8〜10の表記に合わせる）
STATUS = {
    "r1": ("accepted", "watch", "rejected", "nodata"),
    "r2": ("formal", "conditional", "watch", "excluded", "nodata"),
    "r3": ("adopted", "watch", "excluded", "nodata"),
    "r4": ("accepted", "watch", "rejected", "nodata"),
}
FORMAL = {"r1": "accepted", "r2": "formal", "r3": "adopted", "r4": "accepted"}
JST_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+09:00$")
STAKE = 100.0


def path(*p):
    return os.path.join(DATA, *p)


def load(rel, default=None):
    f = path(rel)
    if not os.path.exists(f):
        return default
    with open(f, encoding="utf-8") as fh:
        return json.load(fh)


def save(rel, obj):
    f = path(rel)
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, sort_keys=False)
        fh.write("\n")


def now_jst():
    return datetime.now(JST).replace(microsecond=0).isoformat()


def parse(ts):
    return datetime.fromisoformat(ts)


def no_vig(prices):
    """prices: {'L':1.5,'D':4.0,'R':6.0} → 控除率を除いた確率と控除率"""
    inv = {k: 1 / v for k, v in prices.items() if v}
    s = sum(inv.values())
    return {k: v / s for k, v in inv.items()}, s - 1


# ---------------- 精算 ----------------
def settle_entry(entry, match):
    """match の確定結果から ledger エントリの精算値を返す（未確定なら None）。"""
    res = match.get("result") or {}
    st = match.get("status")
    if st in ("cancelled", "postponed_void", "abandoned_void"):
        return dict(outcome="void", payout=entry["stake"], profit=0.0)
    if st != "final" or not res.get("winner"):
        return None
    sel = entry["selection_key"]
    win = res["winner"]
    market = entry.get("market", "1X2")
    if market in ("DNB",) and win == "D":
        return dict(outcome="void", payout=entry["stake"], profit=0.0)
    if entry.get("odds_taken") is None:
        # 旧移行カード：オッズ証拠なし → 勝敗だけ付けて金額は未計算（補完・0円扱い・負け扱い禁止）
        return dict(outcome="win" if sel == win else "loss", payout=None, profit=None, amount_missing=True)
    if sel == win:
        payout = round(entry["stake"] * entry["odds_taken"], 2)
        return dict(outcome="win", payout=payout, profit=round(payout - entry["stake"], 2))
    return dict(outcome="loss", payout=0.0, profit=round(-entry["stake"], 2))


def summarize(entries, matches):
    """1ロジック分の正式採用エントリから収支を集計（$100単利・複利参考値・1/4ケリー）。"""
    s = dict(formal=0, settled=0, win=0, loss=0, void=0, pending=0, staked=0.0, returned=0.0,
             net=0.0, roi=None, amount_missing=0, hit_rate=None)
    seq = []
    for e in entries:
        s["formal"] += 1
        r = e.get("result")
        if not r:
            s["pending"] += 1
            continue
        s["settled"] += 1
        s[r["outcome"]] += 1
        if r.get("amount_missing"):
            s["amount_missing"] += 1
            continue
        if r["outcome"] == "void":
            continue
        s["staked"] += e["stake"]
        s["returned"] += r["payout"]
        s["net"] += r["profit"]
        m = matches.get(e["match_id"], {})
        seq.append((m.get("start_jst", e["locked_at"]), e["odds_taken"], r["outcome"], e.get("prior_prob")))
    s["staked"] = round(s["staked"], 2); s["returned"] = round(s["returned"], 2); s["net"] = round(s["net"], 2)
    if s["staked"]:
        s["roi"] = round(s["net"] / s["staked"] * 100, 2)
    dec = s["win"] + s["loss"]
    if dec:
        s["hit_rate"] = round(s["win"] / dec * 100, 1)
    # 複利（参考値）：開始時刻順、資金$100から毎回全額
    seq.sort(key=lambda x: x[0])
    bank = 100.0
    for _, o, out, _ in seq:
        bank = bank * o if out == "win" else 0.0 if out == "loss" else bank
        if bank == 0:
            break
    s["compound_ref"] = round(bank, 2)
    # 1/4ケリー：試合前に固定した prior_prob があるものだけ
    kb, kbets, kskip = 100.0, 0, 0
    for _, o, out, p in seq:
        if p is None:
            kskip += 1
            continue
        f = ((p * o - 1) / (o - 1)) / 4 if o > 1 else 0
        if f <= 0:
            kskip += 1
            continue
        stake = kb * f
        kbets += 1
        kb = kb + stake * (o - 1) if out == "win" else kb - stake
    s["kelly_quarter"] = dict(bankroll=round(kb, 2), profit=round(kb - 100, 2), bets=kbets, skipped=kskip)
    return s
