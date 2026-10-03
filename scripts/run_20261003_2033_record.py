"""run-20261003-2033 の automation-runs 記録（41項目チェックリスト＋⑤のcomplete段階）。使い方: python scripts/run_20261002_0600_record.py"""
import json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core
from rmc.build import build

RUN_ID = "run-20261003-2033"
o = json.load(open("/home/claude/dd/run_out.json", encoding="utf-8"))
inv = core.load(f"snapshots/{RUN_ID}/inventory.json")
bst = core.load("odds_feed/status.json"); tst = core.load("odds_feed/tennis_status.json"); bcs = core.load("bc/feed/status.json", {})
scr = core.load("discovery/latest.json"); RL = scr["run_log"]; ST = RL["complete段階"]
matches = core.load("matches.json")
LOCK = open("/home/claude/dd/lock.txt").read().strip()
H24 = core.parse(LOCK).timestamp() + 24 * 3600
runs = core.load("automation-runs.json")
prev = runs[-1]
# coverage を最終の analysis から再計算（重複統合後）
odds_mids = {x["match_id"] for x in core.load("odds_snapshots.json")}
ana = {lg: core.load(f"analysis/{lg}.json")["rows"] for lg in core.LOGICS}
coverage = {}
for mid in inv["match_ids"]:
    sp = matches[mid]["sport"]
    c = coverage.setdefault(sp, dict(event_count=0, priced_upcoming_count=0, market_count=0, in_24h=0, fresh_priced=0))
    c["event_count"] += 1
    c["in_24h"] += int(core.parse(matches[mid]["start_jst"]).timestamp() <= H24)
    if mid in odds_mids:
        c["priced_upcoming_count"] += 1; c["market_count"] += 1
fresh = {r["match_id"] for r in ana["r1"] if r.get("priced")}
for mid in inv["match_ids"]:
    coverage[matches[mid]["sport"]]["fresh_priced"] += int(mid in fresh)
for lg in core.LOGICS:
    for r in ana[lg]:
        sp = matches[r["match_id"]]["sport"]
        lc = coverage[sp].setdefault(lg, dict(screened=0, deep_dive=0, formal=0, formal_floor=0, watch=0, rejected=0, nodata=0))
        lc["screened"] += 1; lc["deep_dive"] += int(bool(r.get("deep_dive")))
        s = r["status"]
        lc["formal" if s == core.FORMAL[lg] else "watch" if s in ("watch", "conditional") else "nodata" if s == "nodata" else "rejected"] += 1
        lc["formal_floor"] += int(s == core.FORMAL[lg] and r.get("pick_type") == "sport_floor")
for sp, c in coverage.items():
    for lg in core.LOGICS:
        lc = c[lg]
        if c["priced_upcoming_count"] and not lc["deep_dive"]:
            lc["deep_dive_waiver"] = ("今回の公開配信に価格がなく（前回取得値のみ）今回の深掘り対象外" if not c["fresh_priced"]
                                      else "24時間以内の試合がなく、次回以降の定時更新で深掘り" if not c["in_24h"]
                                      else "自動取得元（LiveScore・tennisexplorer）に行データがなく、Web深掘りは⑤のTier1を優先したため枠外（次回の対象）")
CL = {f"{i:02d}": False for i in range(1, 42)}
for k in ("01", "02", "03", "06", "07", "08", "09", "10", "11", "13", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
          "28", "29", "30", "31", "32", "33"):
    CL[k] = True
nset = len(o["settled"]); nres = sum(1 for r in o["results"] if r[1] == "final")
unk = [r for r in o["results"] if r[1] != "final"]
t2 = RL["F_未完了_Tier別"]["Tier2"]; t3 = RL["F_未完了_Tier別"]["Tier3"]
newc = {lg: collections.Counter(x[4] for x in v) for lg, v in o["new"].items()}
bot = json.load(open("/home/claude/dd/bottleneck.json", encoding="utf-8"))
notes = {
    "01": f"手動実行（ユーザー指示）。20:33 JST 起動、start_sha 822914a。前回記録 run-20261002-0600（partial）以降の実行なし → 前回 blockers を carried_blockers に引継ぎ、未精算100試合を最優先で確認。⑤スクリーニング基準時刻 {scr['locked_at']}、①〜④判定ロック {LOCK}",
    "02": f"読み替え表の方法：配信が2時間超（17:33）だったため odds-fetch を workflow_dispatch で再取得し、公開配信 Bovada {bst.get('taken_at')}（{bst.get('events')}件・価格あり{bst.get('priced')}件）・tennisexplorer {tst.get('taken_at')}（{tst.get('matches')}試合・ブック別{tst.get('with_book')}）を基準インベントリにした。feed_id・名前照合で重複0件。BET CHANNEL配信（VPS）は {bcs.get('taken_at')} の失敗のまま",
    "03": "読み替え表の方法：カジ旅・遊雅堂（ログイン必要）・bet365直接（クラウド不可）は sources に確認不能と理由を記録。テニスは tennisexplorer 経由のブック別値（bet365含む）を external_market に保存",
    "04": "Bovada・tennisexplorer 掲載の全競技と⑤の日程ソース（LiveScore・UEFA・FIFA・Liquipedia・VLR）を①〜④で全件走査。深掘りは⑤Tier1（Web・サブエージェント8）＋自動取得の行データ（LiveScore・tennisexplorer）のある試合。行データの無い24時間以内・価格ありの試合（MMA・ボクシング・アメフト・卓球・バレー等）はWeb深掘り枠外",
    "05": "eスポーツは Bovada 掲載（CS2・LoL・Dota 2・VALORANT・R6・King of Glory）と Liquipedia 日程（MLBB 等）を全件走査。行データ（facts）のある試合のみ深掘り判定",
    "06": "競技別に event_count／priced_upcoming_count／market_count を coverage に記録。消えた競技（スヌーカー・バドミントン）は sports_disappeared に理由",
    "09": "読み替え表の方法：CLV・締切前オッズ・calibration・オッズ帯ROIは build が summary.analytics に自動計算",
    "10": "読み替え表の方法：同上（opening／closing／CLV）",
    "11": "競技ごとに競技内で判定（全競技横並びの上位抽出なし）。通常基準0件の競技は rmc.select.apply_floor で競技内最上位を競技枠",
    "12": f"⑤Tier1のうち web 項目が未取得の70件をWeb深掘り（サブエージェント8・大会単位）。①〜④の深掘りは facts のある試合（⑤候補＋自動取得の行データで今回 {len(o['added_facts'])}件追補）。24時間以内・価格ありの全件には届かない",
    "13": "一次除外は格差値・オッズ・必要勝率・独立推定の有無・価格帯・時間窓など具体理由を記録",
    "14": "⑤Tier1は deep5 全項目＋反対材料10項目（未確認は finding 冒頭に「未確認：理由」）。①〜④の自動取得行データの試合は直近10・H2H（取得元の範囲）・60日共通相手（form内照合）まで、欠場・ロスターはWeb未確認として missing/risks に明記",
    "15": "eスポーツの深掘り（⑤一次候補の CS2）で BO・LAN・ロスター・ランク・H2H を記録。veto・確定mapは未発表で unavailable",
    "16": f"新規正式採用 ①{len(o['new']['r1'])}・②{len(o['new']['r2'])}・③{len(o['new']['r3'])}・④{len(o['new']['r4'])}（うち競技枠 ①{newc['r1'].get('sport_floor',0)}・②{newc['r2'].get('sport_floor',0)}・③{newc['r3'].get('sport_floor',0)}・④{newc['r4'].get('sport_floor',0)}）。②③④のテニスは Tennis Abstract Elo（外部モデル）、他は log5（市場差15pt超は不採用）",
    "17": f"開始済み未確定の正式カード100試合を全件確認：確定{nres}試合＋棄権無効1試合（{nset}エントリ精算）。結果未確定1試合（CrossFire XROCK-KINGZERO：Liquipedia 429・CFML公式取得不可・他に結果ソースなし）は result_pending_reason を記録して次回確認",
    "18": "テニス83試合は tennisexplorer 結果一覧（専門結果DB・odds-fetch に結果取得を追加して取得）、欧州ホッケー・サッカーは LiveScore（ライブスコア）、LNBP 2試合は地元紙（agssports・El Imparcial）。スニペットのみの確定なし",
    "19": "テニスは配信登録時と同じ tennisexplorer match-detail ID で照合（開始時刻のずれ・日程繰下げは同一IDで確認）。LiveScore は競技・開始±30分・両チーム名・向き（ホーム/アウェイ）で照合。LNBP は連日開催の Game1 を日付・会場で確認",
    "21": "同じ match_id の全ロジック・経験値取引へ反映。テニスの途中棄権4試合：1セット完了後の3試合は試合成立で通常精算（前例 m20260928-7ac3f1df）、第1セット途中の Potapova-Kraus は無効（返金）",
    "27": "敗戦カードは reviews/<entry_id>.md に post-match review（variance/structural 判定・1敗で係数変更なし）",
    "34": "commit/push後に確認", "35": "push後に確認", "36": "push後に確認", "37": "push後に確認",
    "38": "push後に確認", "39": "push後に確認", "40": "報告送信後に確定", "41": "上記未完了があるため更新完了とはしない",
    "⑤": f"⑤ complete段階：①探索={ST['①探索complete']}／②重要候補={ST['②重要候補complete']}／③全候補={ST['③全候補complete']}。Tier1未完了{RL['F_未完了_Tier別']['Tier1']}件（Web検索のセッション上限200回に到達し主力欠場等が未確認）・Tier2残{t2}件／Tier3残{t3}件は次回へ引き継ぎ",
}
blockers = [f"⑤：Tier1未完了{RL['F_未完了_Tier別']['Tier1']}件（主に「主力欠場」が未確認）→ ②重要候補complete 不成立。ボトルネック：{bot['summary']}",
            f"⑤：Tier2残{t2}件／Tier3残{t3}件（次回へ引き継ぎ）",
            "Web検索がセッション上限（200回）に到達：Tier1深掘りの途中（ホッケー担当の後半4試合はほぼ未調査）で打ち切り。次回は1回あたりのTier1件数を絞るか、クラブ公式・リーグ公式の取得を Actions 側で自動化する必要あり",
            "深掘りが24時間以内・価格ありの全試合に届かない：自動取得の行データ（LiveScore・tennisexplorer）が無い競技（MMA・ボクシング・アメフト・卓球・バレー・一部eスポーツ）はWeb深掘り枠外（項目4・12・14）",
            "独立モデルは Tennis Abstract Elo（テニス）のみ外部。他競技は log5（内製・相手強度未補正）、サッカー1X2は3択モデルなしで②③④は通常基準の判定不能（項目8〜10）",
            "BET CHANNEL配信（VPS）が失敗のまま、BET CHANNEL専用eスポーツ（MLBB・CrossFire等）の価格なし（項目2・5）",
            "結果未確定1試合（CrossFire XROCK-KINGZERO 9/30）は result_pending_reason を記録して次回確認（項目17）"]
run = dict(run_id=RUN_ID, slot="20:33", started_at="2026-10-03T20:33:10+09:00", finished_at=core.now_jst(),
           start_sha="822914a", status="partial", previous_run_ok=False, carried_blockers=prev.get("blockers", []),
           inventory_match_ids=inv["match_ids"], coverage=coverage,
           sports_disappeared={sp: "今回の配信・日程ソースに判定時刻以降の未開始試合なし（前回分は開始済み・終了）" for sp in prev["coverage"] if sp not in coverage},
           sources=dict(betchannel=f"確認不能：VPS配信 data/bc/feed が {bcs.get('taken_at')} に失敗したまま、クラウドからは直接接続できない（ユーザー指示によりBovada等の公開配信で代替）",
                        kajitabi="確認不能：ログインが必要（クラウドから接続不可）",
                        bet365="確認不能（直接）：クラウドから接続不可。テニスのみ tennisexplorer 経由で bet365 値を取得",
                        yuugado="確認不能：ログインが必要（クラウドから接続不可）",
                        bovada=f"取得：公開coupon JSON {bst.get('taken_at')}（{bst.get('events')}件・odds-fetch を workflow_dispatch で再取得）",
                        tennisexplorer=f"取得：{tst.get('taken_at')}（{tst.get('matches')}試合・ブック別 {tst.get('with_book')}試合）"),
           deep_dive_bottleneck=bot, discovery=dict(locked_at=scr["locked_at"], run_log={k: RL[k] for k in RL if k != "日程ソース照合"}, complete_stages=ST),
           publish_status=dict(analysis="success", local_commit="pending", github_push="pending", rmc_public="pending"),
           feed_duplicates_skipped=o["dup"], facts_written=len(o["added_facts"]) + 70,
           blockers=blockers, checklist=CL, checklist_notes=notes)
runs.append(run)
core.save("automation-runs.json", runs)
build()
print("ok", sum(CL.values()), "/41")
