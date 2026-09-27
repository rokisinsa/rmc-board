"""RMC データ検証。チェックリスト（CHECKLIST.md）のうち機械判定できる項目をすべて検査する。
使い方: python -m rmc.validate [--base <git ref>]   エラーが1件でもあれば終了コード1。"""
import json, subprocess, sys
from .core import (load, LOGICS, STATUS, FORMAL, JST_RE, parse, summarize, no_vig)

RESULT_SOURCE_RANK = ("official_team", "league_official", "results_db", "livescore")
BANNED_REASONS = {"no_deep_dive_signal", "", None}
DEEP_FIELDS_COMMON = ("title", "competition", "date", "start_jst", "matchup", "ranking", "h2h", "recent_form",
                      "venue", "lineup", "odds", "odds_exact", "required_prob", "prior_prob", "edge_or_ev",
                      "external_market", "rationale", "risks", "missing", "source_urls")
DEEP_FIELDS_ESPORTS = ("format", "lan_online", "roster", "map_pool", "veto", "patch", "series_h2h", "map_h2h", "rating")
ESPORTS = {"CS2", "VALORANT", "Dota 2", "LoL", "Rainbow Six", "Honor of Kings", "Overwatch 2", "Rocket League",
           "Call of Duty", "PUBG", "Mobile Legends", "StarCraft II", "EA FC", "eBasketball", "Arena of Valor",
           "Warcraft", "Hearthstone", "Halo", "Fortnite", "World of Tanks"}


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, code, msg):
        self.errors.append(f"[{code}] {msg}")

    def warn(self, code, msg):
        self.warnings.append(f"[{code}] {msg}")


def git_show(ref, rel):
    try:
        out = subprocess.run(["git", "show", f"{ref}:data/{rel}"], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)
    except Exception:
        return None


def filled(v):
    if v is None or v == "" or v == []:
        return False
    if isinstance(v, dict) and v.get("unavailable") is not None:
        return bool(v.get("reason"))  # unavailable は理由必須
    return True


def check_matches(rep, matches):
    for mid, m in matches.items():
        for k in ("sport", "competition", "start_jst", "left", "right", "status"):
            if m.get(k) in (None, ""):
                rep.err("MATCH_NULL", f"{mid}: {k} が空")
        if m.get("start_jst") and not JST_RE.match(m["start_jst"]):
            rep.err("MATCH_JST", f"{mid}: start_jst がJST ISO形式でない ({m['start_jst']})")
        if m.get("status") == "final":
            r = m.get("result") or {}
            if r.get("winner") not in ("L", "D", "R"):
                rep.err("RESULT_WINNER", f"{mid}: final だが winner がない")
            if r.get("source_rank") not in RESULT_SOURCE_RANK:
                rep.err("RESULT_SOURCE", f"{mid}: 結果ソース区分が不正（予想サイト・スニペットでの確定は禁止）")
            if not r.get("source_url"):
                rep.err("RESULT_SOURCE", f"{mid}: 結果の source_url がない")
            if not r.get("identity_checked"):
                rep.err("RESULT_IDENTITY", f"{mid}: 試合同一性（日付・時刻・大会・ラウンド・相手・H/A）確認フラグがない")


def check_odds(rep, odds, matches):
    seen = set()
    for o in odds:
        key = (o.get("match_id"), o.get("source"), o.get("taken_at"), o.get("market"))
        if key in seen:
            rep.err("ODDS_DUP", f"重複オッズスナップショット {key}")
        seen.add(key)
        if o.get("match_id") not in matches:
            rep.err("ODDS_MATCH", f"オッズの match_id {o.get('match_id')} が matches にない")
        if not o.get("source") or not o.get("taken_at"):
            rep.err("ODDS_SOURCE", f"{o.get('match_id')}: オッズの source / taken_at が空")
        if o.get("taken_at") and not JST_RE.match(o["taken_at"]):
            rep.err("ODDS_JST", f"{o.get('match_id')}: taken_at がJST形式でない")


def check_analysis(rep, lg, ana, matches, inventory, odds_idx):
    if not ana:
        rep.err("ANALYSIS_MISSING", f"{lg}: 分析ファイルがない")
        return
    rows = ana.get("rows", [])
    ids = [r.get("match_id") for r in rows]
    if len(ids) != len(set(ids)):
        rep.err("ANALYSIS_DUP", f"{lg}: 同じ match_id が複数行ある")
    missing = set(inventory) - set(ids)
    if missing:
        rep.err("SCREEN_INCOMPLETE", f"{lg}: 走査漏れ {len(missing)} 件（例: {sorted(missing)[:3]}）")
    for r in rows:
        mid = r.get("match_id")
        if mid not in matches:
            rep.err("ANALYSIS_MATCH", f"{lg}: 未知の match_id {mid}")
            continue
        if r.get("status") not in STATUS[lg]:
            rep.err("ANALYSIS_STATUS", f"{lg}/{mid}: 判定値 {r.get('status')} は {STATUS[lg]} のどれでもない")
        if r.get("reason") in BANNED_REASONS or str(r.get("reason", "")).strip() == "no_deep_dive_signal":
            rep.err("REASON_QUALITY", f"{lg}/{mid}: 具体的な判定理由がない")
        if r.get("status") != "nodata" and mid in odds_idx and r.get("priced") is False:
            rep.warn("PRICED_FLAG", f"{lg}/{mid}: オッズがあるのに priced=false")
        if r.get("deep_dive"):
            d = r.get("deep_dive_detail") or {}
            need = DEEP_FIELDS_COMMON + (DEEP_FIELDS_ESPORTS if matches[mid]["sport"] in ESPORTS else ())
            lack = [f for f in need if not filled(d.get(f))]
            if lack:
                rep.err("DEEP_DIVE_FIELDS", f"{lg}/{mid}: deep_dive 必須項目が空（値か unavailable+理由を入れる）: {lack}")
            cut = ana.get("decided_at") or ana.get("run_started_at")
            if d.get("data_as_of") and cut and parse(d["data_as_of"]) > parse(cut):
                rep.err("FUTURE_LEAK", f"{lg}/{mid}: data_as_of が判定確定時刻（decided_at）より後")
            if d.get("data_as_of") and parse(d["data_as_of"]) >= parse(matches[mid]["start_jst"]):
                rep.err("FUTURE_LEAK", f"{lg}/{mid}: 試合開始後のデータで事前分析している")
        if r.get("status") == FORMAL[lg]:
            if not r.get("deep_dive"):
                rep.err("FORMAL_NO_DEEP", f"{lg}/{mid}: deep_dive なしで正式採用")


def check_ledger(rep, lg, ledger, matches, base_ledger):
    ids = [e.get("entry_id") for e in ledger]
    if len(ids) != len(set(ids)):
        rep.err("LEDGER_DUP", f"{lg}: entry_id が重複")
    for e in ledger:
        eid = e.get("entry_id")
        m = matches.get(e.get("match_id"))
        if not m:
            rep.err("LEDGER_MATCH", f"{lg}/{eid}: match_id が matches にない")
            continue
        legacy = e.get("legacy_migrated") is True
        for k in ("market", "selection", "selection_key", "stake", "locked_at", "odds_source"):
            if e.get(k) in (None, "") and not (legacy and k == "odds_source"):
                rep.err("LEDGER_NULL", f"{lg}/{eid}: {k} が空")
        if not legacy:
            if not isinstance(e.get("odds_taken"), (int, float)):
                rep.err("EXACT_ODDS", f"{lg}/{eid}: 新規正式採用に exact odds がない（レンジの一点化も禁止）")
            if e.get("locked_at") and m.get("start_jst") and parse(e["locked_at"]) >= parse(m["start_jst"]):
                rep.err("LOCK_AFTER_START", f"{lg}/{eid}: 試合開始後にロックされている")
        elif e.get("odds_taken") is None and e.get("odds_range"):
            pass  # 旧データのレンジはそのまま保持（中央値補完はしない）
        # 結果伝播
        if m.get("status") == "final" and not e.get("result"):
            rep.err("RESULT_PROPAGATION", f"{lg}/{eid}: 試合は final なのに結果未反映")
        if e.get("result"):
            from .core import settle_entry
            exp = settle_entry(e, m)
            got = {k: e["result"].get(k) for k in ("outcome", "payout", "profit")}
            if exp and any(exp.get(k) != got.get(k) for k in ("outcome", "payout", "profit")):
                rep.err("SETTLEMENT", f"{lg}/{eid}: 精算値が再計算と不一致 {got} != {exp}")
    # locked 保護（append-only）
    if base_ledger is not None:
        cur = {e["entry_id"]: e for e in ledger}
        for old in base_ledger:
            new = cur.get(old["entry_id"])
            if new is None:
                rep.err("LOCKED_DELETED", f"{lg}/{old['entry_id']}: 既存の正式採用が削除された")
                continue
            for k, v in old.items():
                if k == "result" and v is None:
                    continue
                if new.get(k) != v:
                    rep.err("LOCKED_MODIFIED", f"{lg}/{old['entry_id']}: locked 項目 {k} が書き換えられた")


def check_runs(rep, runs, ana_by_logic):
    if not runs:
        rep.err("RUNS_EMPTY", "automation-runs.json に記録がない")
        return
    last = runs[-1]
    for k in ("run_id", "started_at", "start_sha", "status", "coverage", "sources"):
        if last.get(k) in (None, ""):
            rep.err("RUN_FIELD", f"最新run: {k} が空")
    for site in ("betchannel", "kajitabi", "bet365", "yuugado"):
        v = (last.get("sources") or {}).get(site)
        if v is None:
            rep.err("SOURCE_STATUS", f"最新run: {site} の確認結果（取得/確認不能+理由）が記録されていない")
    if last.get("status") not in ("complete", "partial", "failed"):
        rep.err("RUN_STATUS", f"最新run: status は complete/partial/failed のいずれか（{last.get('status')}）")
    claims_complete = last.get("status") == "complete"
    if not claims_complete and not last.get("blockers"):
        rep.err("RUN_BLOCKERS", "最新runが complete でないのに blockers（未完了項目）が記録されていない")
    gate = rep.err if claims_complete else rep.warn
    for sport, c in (last.get("coverage") or {}).items():
        for lg in LOGICS:
            lc = c.get(lg, {})
            if c.get("event_count", 0) > 0 and lc.get("screened", 0) == 0:
                rep.err("COVERAGE_SCREEN", f"{sport}: event_count>0 なのに {lg} screened=0")
            if c.get("priced_upcoming_count", 0) > 0 and lc.get("deep_dive", 0) == 0 and not lc.get("deep_dive_waiver"):
                gate("COVERAGE_DEEPDIVE", f"{sport}: priced_upcoming>0 なのに {lg} deep_dive=0（理由の記録もない）")
    if claims_complete:
        undone = [k for k, v in (last.get("checklist") or {}).items() if v is not True]
        if len(last.get("checklist") or {}) < 41 or undone:
            rep.err("CHECKLIST", f"complete と記録されているがチェックリスト未完了: {undone or '41項目の記録なし'}")
    if len(runs) >= 2:
        prev = runs[-2]
        gone = set(prev.get("coverage", {})) - set(last.get("coverage", {}))
        for sp in gone:
            if sp not in (last.get("sports_disappeared") or {}):
                rep.err("SPORT_DISAPPEARED", f"前回あった競技 {sp} が理由なく消えた")


def check_independence(rep, ana_by_logic):
    rows = {lg: {r["match_id"]: r for r in (a or {}).get("rows", [])} for lg, a in ana_by_logic.items()}
    for mid in rows.get("r2", {}):
        a, b = rows["r2"].get(mid, {}), rows.get("r3", {}).get(mid, {})
        if a.get("deep_dive") and b.get("deep_dive") and a.get("rationale") and a.get("rationale") == b.get("rationale"):
            rep.err("INDEPENDENCE", f"{mid}: ②と③の分析文が同一（コピペ禁止）")
    for mid, r in rows.get("r4", {}).items():
        if r.get("deep_dive") and r.get("base_prob") is not None and r.get("base_prob") == r.get("market_prob"):
            rep.err("INDEPENDENCE", f"{mid}: ④の base_probability が market_probability の流用")


def run(base=None):
    rep = Report()
    matches = load("matches.json", {})
    odds = load("odds_snapshots.json", [])
    runs = load("automation-runs.json", [])
    inventory = (runs[-1].get("inventory_match_ids") if runs else None) or []
    if len(inventory) != len(set(inventory)):
        rep.err("INVENTORY_DUP", "インベントリに重複 match_id")
    odds_idx = {o["match_id"] for o in odds}
    check_matches(rep, matches)
    check_odds(rep, odds, matches)
    ana = {lg: load(f"analysis/{lg}.json") for lg in LOGICS}
    for lg in LOGICS:
        check_analysis(rep, lg, ana[lg], matches, inventory, odds_idx)
        base_ledger = git_show(base, f"ledger/{lg}.json") if base else None
        check_ledger(rep, lg, load(f"ledger/{lg}.json", []), matches, base_ledger)
    base_exp = git_show(base, "ledger/experience.json") if base else None
    check_ledger(rep, "experience", load("ledger/experience.json", []), matches, base_exp)
    check_runs(rep, runs, ana)
    check_independence(rep, ana)
    # profit audit
    summ = load("summary.json")
    recomputed = {lg: summarize(load(f"ledger/{lg}.json", []), matches) for lg in LOGICS + ("experience",)}
    if summ is None or summ.get("logics") != recomputed:
        rep.err("PROFIT_AUDIT", "summary.json が台帳からの再計算と一致しない（python -m rmc.build を実行）")
    return rep


if __name__ == "__main__":
    base = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else None
    r = run(base)
    for w in r.warnings:
        print("WARN ", w)
    for e in r.errors:
        print("ERROR", e)
    print(f"errors={len(r.errors)} warnings={len(r.warnings)}")
    sys.exit(1 if r.errors else 0)
