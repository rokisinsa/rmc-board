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
ESPORTS = {"CS2", "VALORANT", "King of Glory", "CrossFire", "StarCraft: BW", "Dota 2", "LoL", "Rainbow Six", "Honor of Kings", "Overwatch 2", "Rocket League",
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
    # 新規エントリは判定時刻から24時間以内に始まる試合だけ
    from .core import within_horizon, HORIZON_HOURS
    base_ids = {e["entry_id"] for e in (base_ledger or [])}
    for e in ledger:
        m = matches.get(e.get("match_id")) or {}
        if base_ledger is not None and e["entry_id"] not in base_ids and e.get("locked_at") and m.get("start_jst") \
                and not within_horizon(e["locked_at"], m["start_jst"]):
            rep.err("FORMAL_HORIZON", f"{lg}/{e['entry_id']}: 開始がロックから{HORIZON_HOURS}時間より先の試合を正式採用している")
    # locked 保護（append-only）
    if base_ledger is not None:
        cur = {e["entry_id"]: e for e in ledger}
        archived = {e["entry_id"] for e in load(f"ledger_archive/{lg}.json", [])}  # ユーザー指示で台帳から外した分（保管済み）
        for old in base_ledger:
            new = cur.get(old["entry_id"])
            if new is None and old["entry_id"] in archived:
                continue
            if new is None:
                rep.err("LOCKED_DELETED", f"{lg}/{old['entry_id']}: 既存の正式採用が削除された")
                continue
            for k, v in old.items():
                if k == "result" and v is None:
                    continue
                if new.get(k) != v:
                    rep.err("LOCKED_MODIFIED", f"{lg}/{old['entry_id']}: locked 項目 {k} が書き換えられた")


OVERDUE_HOURS = 4  # 開始からこの時間を過ぎた正式採用は、定時更新で結果を反映していないとエラー


def check_results_overdue(rep, matches, now=None):
    """開始から OVERDUE_HOURS 時間を過ぎても未精算の正式採用があれば止める（定時更新での結果反映漏れ防止）。
    本当に結果が出ていない（延期・長時間試合・結果未公表）ときは matches の result_pending_reason に理由を書けば通る。"""
    from .core import now_jst
    now = parse(now or now_jst())
    for lg in LOGICS + ("experience",):
        for e in load(f"ledger/{lg}.json", []):
            if e.get("result") or e.get("withdrawn"):
                continue
            m = matches.get(e.get("match_id")) or {}
            if not m.get("start_jst") or m.get("result_pending_reason"):
                continue
            h = (now - parse(m["start_jst"])).total_seconds() / 3600
            if h > OVERDUE_HOURS:
                rep.err("RESULT_OVERDUE", f"{lg}/{e['entry_id']}: 開始から{h:.0f}時間経過しているのに結果未反映（結果を確認して精算するか、result_pending_reason に理由）")


def check_facts_coverage(rep, matches):
    """未確定の正式採用カードは、事実（直近成績・H2H・60日以内の共通相手）を徹底取得済みであること。
    取れない場合は unavailable に理由が書いてあれば通る（数字を作らないため）。"""
    pend = set()
    for lg in LOGICS + ("experience",):
        for e in load(f"ledger/{lg}.json", []):
            if e.get("result") is None:
                pend.add(e["match_id"])
    import os
    from .core import path as _path
    for mid in sorted(pend):
        f = _path("facts", f"{mid}.json")
        if not os.path.exists(f):
            rep.err("FACTS_COVERAGE", f"{mid}: 正式採用（未確定）なのに facts がない")
            continue
        x = json.load(open(f, encoding="utf-8"))
        un = " ".join(str(k) for k in (x.get("unavailable") or {}))
        for side in ("left", "right"):
            if len((x.get(side) or {}).get("form") or []) < 5 and "form" not in un and f"{side}" not in un:
                rep.err("FACTS_COVERAGE", f"{mid}: {side}.form が5試合未満（理由の unavailable も無い）")
        if not (x.get("h2h") or []) and "h2h" not in un:
            rep.err("FACTS_COVERAGE", f"{mid}: h2h が空（初対戦の確認根拠も無い）")
        nh = len((x.get("left") or {}).get("history") or []) + len((x.get("right") or {}).get("history") or [])
        if nh == 0 and not any(w in un for w in ("history", "common")):
            rep.err("FACTS_COVERAGE", f"{mid}: 共通相手用の60日 history が空（確認結果の unavailable も無い）")


def check_sport_floor(rep, matches):
    """全競技（リアル・eスポーツ）から①〜④それぞれ必ず正式採用が出ているか（ユーザー指示 2026-09-29）。"""
    from . import select
    for lg in LOGICS:
        a = load(f"analysis/{lg}.json") or {}
        locked = max(a.get("decided_at") or "", a.get("floor_applied_at") or "")
        if not locked:
            continue
        for sp in select.missing_floor(lg, a.get("rows", []), matches, locked):
            rep.err("SPORT_FLOOR", f"{lg}/{sp}: 対象試合があるのに正式採用が1件もない（rmc.select.apply_floor で競技枠を出す）")


D5_START = "2026-09-30T05:00:00+09:00"   # ⑤ 格差候補発見エンジンの必須化（この時刻以降の定時更新から）


def check_discovery(rep, matches, ana_by_logic):
    """⑤：毎回、①〜④より前に全試合を⑤に通し、候補は完全深掘り・反対材料確認ののち確定し、最後にオッズを付けていること。"""
    from . import discover as d5
    decided = max(((a or {}).get("decided_at") or "") for a in ana_by_logic.values()) if ana_by_logic else ""
    if not decided or decided < D5_START:
        return
    scr = load("discovery/latest.json")
    if not scr:
        rep.err("DISCOVERY", "⑤の結果（data/discovery/latest.json）がない"); return
    if scr.get("stage") != "finalized":
        rep.err("DISCOVERY", "⑤が確定（finalize）まで進んでいない")
    if abs((parse(scr["locked_at"]) - parse(decided)).total_seconds()) > 6 * 3600:
        rep.err("DISCOVERY", f"⑤の判定時刻 {scr.get('locked_at')} が今回の①〜④ {decided} と別の回")
    if scr.get("odds_used_in_screening") is not False:
        rep.err("DISCOVERY", "⑤の候補発見でオッズを使っていない証跡（odds_used_in_screening=false）がない")
    if not scr.get("odds_attached_at") or scr["odds_attached_at"] < scr.get("screened_at", ""):
        rep.err("DISCOVERY", "オッズは⑤の候補確定のあとに付ける（odds_attached_at が screened_at より前か無い）")
    fc = scr.get("fixture_check") or {}
    last_run = (load("automation-runs.json", []) or [{}])[-1]
    if not fc.get("all_ok"):
        bad = [k for k, v in (fc.get("sources") or {}).items() if not v.get("ok")]
        (rep.err if last_run.get("status") == "complete" else rep.warn)(
            "DISCOVERY", f"⑤の日程母集団の複数ソース照合が正常終了していない（{bad or '照合結果なし'}）→ 完全走査済み（complete）にできない")
    rows = {r["match_id"]: r for r in scr.get("rows", [])}
    for mid in d5.inventory(matches, scr["locked_at"]):
        if mid not in rows:
            rep.err("DISCOVERY", f"{mid}: 24時間以内の試合が⑤に通されていない")
    claims_complete = last_run.get("status") == "complete"
    run_txt = json.dumps(dict(blockers=last_run.get("blockers"), notes=last_run.get("checklist_notes"),
                              carried=last_run.get("carried_blockers")), ensure_ascii=False)
    has_blocker_note = ("⑤" in run_txt) or ("Tier2残" in run_txt) or ("Tier3残" in run_txt)
    for r in rows.values():
        if any(k in json.dumps(r.get("indicators") or {}) for k in ('"prices"', '"odds', '"nv_')):
            rep.err("DISCOVERY", f"{r['match_id']}: ⑤の指標にオッズ由来の値が入っている")
        if r.get("status") in ("一次候補", "深掘り未完"):
            # complete（＝②重要候補complete以上）の run で Tier1 の未完了は1件も許されない。
            # Tier2/3 の残りは更新を止めないが、blockers か notes に「Tier2残N件／Tier3残N件」等の明示が必要
            if r.get("tier") == 1:
                gate = rep.err if claims_complete or not has_blocker_note else rep.warn
                gate("DISCOVERY", f"{r['match_id']}: Tier1候補が未完了（{r.get('status')}：{str(r.get('reason'))[:60]}）。"
                                  "Tier1が1件でも未完了なら ②重要候補complete＝run status complete は禁止")
            else:
                gate = rep.err if not has_blocker_note else rep.warn
                gate("DISCOVERY", f"{r['match_id']}: Tier{r.get('tier')}候補が未完了（{r.get('status')}）。"
                                  "残す場合は blockers か notes に「Tier2残N件／Tier3残N件」を明示して次回へ引き継ぐ")
        if r.get("status") == "格差候補確定" and (not r.get("support") or r.get("grade") not in ("A", "B")):
            rep.err("DISCOVERY", f"{r['match_id']}: 確定候補に支持材料・⑤-A/B の区分がない")
    # 3段階complete（①探索／②重要候補／③全候補）の宣言と実態の一致
    stages = (scr.get("run_log") or {}).get("complete段階") or {}
    if claims_complete and stages.get("②重要候補complete") is not True:
        rep.err("DISCOVERY", f"run status=complete だが ②重要候補complete の条件を満たしていない（{stages.get('判定根拠')}）")
    if "全候補complete" in run_txt and stages.get("③全候補complete") is not True:
        rep.err("DISCOVERY", "③全候補complete と表示しているが、Tier2/3を含む一次候補全件の深掘りが完了していない（③の表示は禁止）")
    # complete の追加条件：ログの件数整合・重複行なし・JST形式
    rl = scr.get("run_log") or {}
    cons = rl.get("整合性") or {}
    if claims_complete:
        if not rl:
            rep.err("DISCOVERY", "complete なのに⑤の run_log（A〜F）がない")
        if cons.get("深掘り完了_eq_A_B_保留") is not True:
            rep.err("DISCOVERY", "complete なのに 深掘り完了 ≠ ⑤-A＋⑤-B＋保留（件数の整合が取れていない）")
        if cons.get("Tier合計_eq_一次候補") is not True:
            rep.err("DISCOVERY", "complete なのに Tier1+2+3 ≠ 一次候補数")
        if cons.get("重複行", 0) != 0:
            rep.err("DISCOVERY", f"complete なのに母集団に同一試合の重複行が{cons.get('重複行')}組ある")
    for k in ("locked_at", "screened_at", "odds_attached_at"):
        v = scr.get(k)
        if v and not JST_RE.match(v):
            rep.err("DISCOVERY", f"⑤の {k} がJST ISO形式でない（{v}）")
    conf = {m for m, r in rows.items() if r.get("status") == "格差候補確定" and r["start_jst"] > decided}
    for lg, a in ana_by_logic.items():
        seen = {x["match_id"]: x for x in (a or {}).get("rows", [])}
        for mid in conf:
            x = seen.get(mid)
            if not x or not x.get("d5") or not x.get("deep_dive"):
                rep.err("DISCOVERY", f"{lg}/{mid}: ⑤の確定候補が①〜④に深掘り付きで渡されていない（rmc.discover.tag_rows）")


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


def check_facts(rep, matches):
    import glob, os, json as _j
    from . import core as _core
    for f in glob.glob(os.path.join(_core.DATA, "facts", "*.json")):
        mid = os.path.basename(f)[:-5]
        try:
            x = _j.load(open(f, encoding="utf-8"))
        except Exception as e:
            rep.err("FACTS_JSON", f"{mid}: facts が壊れたJSON ({e})"); continue
        if mid not in matches:
            rep.err("FACTS_MATCH", f"{mid}: facts に対応する試合がない")
        for side in ("left", "right"):
            if not isinstance(x.get(side), dict) or not isinstance(x[side].get("form", []), list) or not isinstance(x[side].get("history", []), list):
                rep.err("FACTS_SHAPE", f"{mid}: {side}.form / history は1試合1行のリストにする（docs/FACTS_SPEC.md）")
        if not isinstance(x.get("h2h", []), list):
            rep.err("FACTS_SHAPE", f"{mid}: h2h は1試合1行のリストにする")
        from .facts import enrich
        import copy as _c
        if x.get("calc") != enrich(_c.deepcopy(x), (matches.get(mid) or {}).get("start_jst")).get("calc"):
            rep.err("FACTS_CALC", f"{mid}: 集計（calc）が行データからの再計算と一致しない（python -m rmc.build）")


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
    check_facts(rep, matches)
    check_facts_coverage(rep, matches)
    check_results_overdue(rep, matches)
    check_sport_floor(rep, matches)
    check_discovery(rep, matches, ana)
    # profit audit
    summ = load("summary.json")
    recomputed = {lg: summarize(load(f"ledger/{lg}.json", []), matches) for lg in LOGICS + ("experience",)}
    from .core import gap_bands
    gb = gap_bands({lg: load(f"ledger/{lg}.json", []) for lg in LOGICS + ("experience",)}, load("odds_snapshots.json", []))
    from .core import analytics as _an
    an = _an({lg: load(f"ledger/{lg}.json", []) for lg in LOGICS + ("experience",)}, matches, load("odds_snapshots.json", []), load("odds_closing.json", []))
    led_all = {lg: load(f"ledger/{lg}.json", []) for lg in LOGICS + ("experience",)}
    bt = {lg: {t: summarize([e for e in led_all[lg] if (e.get("pick_type") or "criteria") == t], matches)
               for t in ("criteria", "sport_floor")} for lg in led_all}
    if summ is None or summ.get("logics") != recomputed or summ.get("gap_bands") != gb or summ.get("analytics") != an or summ.get("by_type") != bt:
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
