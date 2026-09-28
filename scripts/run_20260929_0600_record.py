"""run-20260929-0600 の automation-runs 記録（41項目チェックリスト）。使い方: python scripts/run_20260929_0600_record.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core
from rmc.build import build

RUN_ID = "run-20260929-0600"
o = json.load(open("/home/claude/dd/run_out.json", encoding="utf-8"))
inv = core.load(f"snapshots/{RUN_ID}/inventory.json")
bst = core.load("odds_feed/status.json"); tst = core.load("odds_feed/tennis_status.json"); bcs = core.load("bc/feed/status.json", {})
runs = core.load("automation-runs.json")
prev = runs[-1]
CL = {f"{i:02d}": False for i in range(1, 42)}
for k in ("01", "02", "03", "06", "07", "08", "09", "10", "11", "13", "16", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
          "28", "29", "30", "31", "32", "33"):
    CL[k] = True
gone = {sp: "BET CHANNEL配信（data/bc/feed）が503で取得できず、BET CHANNEL専用タイトルの新規掲載を確認できない。登録済みの未開始試合もなし（WoT CQ残り1試合は開始済みで結果待ち）" for sp in o["gone"]}
notes = {
    "01": "06:00枠。05:56 JST起動、start_sha ba0667d（odds-fetch 81d6bd2 を pull）。前回 run-20260928-2320 は partial → blockers を carried_blockers に引継ぎ",
    "02": f"読み替え表の方法：公開配信 Bovada {bst.get('taken_at')}（{bst.get('events')}件・価格あり{bst.get('priced')}件、全21カテゴリ中取得失敗1＝水球404）・tennisexplorer {tst.get('taken_at')}（{tst.get('matches')}試合・ブック別{tst.get('with_book')}）を基準インベントリにし、重複1件（Grêmio表記ゆれ）を統合。取得時刻は判定の約1.5時間前（2時間以内）。BET CHANNEL配信（VPS経由）は {bcs.get('taken_at')} に HTTP 503 で失敗",
    "03": "読み替え表の方法：カジ旅・遊雅堂（ログイン必要）・bet365直接（クラウド不可）は sources に確認不能と理由を記録。テニスは tennisexplorer 経由のブック別値を external_market に保存",
    "04": "Bovada・tennisexplorer に掲載のある全競技（サッカー・テニス・ホッケー・バスケ・野球・アメフト・卓球・ダーツ・スヌーカー・バドミントン・クリケット・バレー）を全件走査。ハンドボール・ラグビー・ボクシング・フットサルは配信0件、水球は404",
    "05": "eスポーツは Bovada 掲載（CS2・Dota 2・VALORANT・LoL）を全件走査し24時間以内・価格あり14試合を深掘り。BET CHANNEL専用タイトル（KoG・MLBB・R6・CrossFire・SC:BW）は配信取得失敗のため前回値・前回判定の引継ぎ",
    "06": "競技別に event_count／priced_upcoming_count／market_count を coverage に記録。消えた競技（Standoff 2・WoT）は sports_disappeared に理由",
    "09": "読み替え表の方法：CLV・締切前オッズ・calibration・オッズ帯ROIは build が summary.analytics に自動計算",
    "10": "読み替え表の方法：同上（opening／closing／CLV）",
    "11": "競技ごとにサブエージェントが競技内で候補を選定（競技横断の上位抽出なし）",
    "12": "今回の新規深掘り112件（テニス42・サッカー16・バスケ14・野球2・アメフト1・ホッケー10・バレー1・クリケット2・ダーツ2・スヌーカー2・バドミントン4・卓球2・eスポーツ14）。ただしテニス40件は tennisexplorer・Tennis Abstract がプロキシで遮断され事実がほぼ取れず、ITF/UTR/Futures（約80件）は深掘り枠外",
    "14": "深掘り112件中、両者5試合以上の直近成績を取れたのは23件。残りは unavailable に理由（取得元の遮断・承認待ち・掲載なし）。事実不足（直近5試合未満）の試合は①でも正式採用しないガードを今回から適用",
    "15": "eスポーツ14件で format・LAN/online・roster・map pool・veto・patch・series/map H2H・rating を記録（既存9件は追補、新規5件）",
    "16": "新規正式採用は①6件（条件を満たす全件）。②③④は独立モデルが取れた試合（NFL Dimers 1件・eスポーツ log5）でも乖離ガード・基準未達で watch 止まり（無理な採用なし）",
    "17": "開始済み未確定の正式カード8件を全件確認：確定6件（①3勝3敗）、結果未公表2件（Bestia Academy-QUINTESSENCIA・Virtus.pro-BOGATYRI）は result_pending_reason を付けて次回再確認",
    "18": "KHL公式・Al Riyadi公式・Sofascore・TNT Sports/totallysnookered・cybersport.ru で確定（スニペットのみの確定なし）",
    "19": "日付・JST時刻・大会・ラウンド・相手を identity_note に記録（オサリバンの相手「Jun」＝蒋俊を特定）",
    "21": "同じ match_id の全ロジック・経験値取引へ反映",
    "27": "①の敗戦3件（オサリバン・趙心童・Al Ittihad）を data/reviews/ に記録（1敗で係数は変えない）",
    "34": "commit/push後に確認", "35": "push後に確認", "36": "push後に確認", "37": "push後に確認",
    "38": "push後に確認", "39": "push後に確認", "40": "報告送信後に確定", "41": "上記未完了があるため定時更新完了とはしない",
}
run = dict(run_id=RUN_ID, slot="06:00", started_at="2026-09-29T05:56:06+09:00", finished_at=core.now_jst(),
           start_sha="ba0667d", status="partial", previous_run_ok=False, carried_blockers=prev.get("blockers", []),
           inventory_match_ids=inv["match_ids"], coverage=o["coverage"], sports_disappeared=gone,
           sources=dict(betchannel=f"確認不能：VPS配信 data/bc/feed が {bcs.get('taken_at')} に HTTP 503 で失敗、クラウドからは直接接続できない（ユーザー指示によりBovada等の公開配信で代替）",
                        kajitabi="確認不能：ログインが必要（クラウドから接続不可）",
                        bet365="確認不能（直接）：クラウドから接続不可。テニスのみ tennisexplorer 経由で bet365 値を取得",
                        yuugado="確認不能：ログインが必要（クラウドから接続不可）",
                        bovada=f"取得：公開coupon JSON {bst.get('taken_at')}（{bst.get('events')}件・GitHub Actions odds-fetch 定時実行）",
                        tennisexplorer=f"取得：{tst.get('taken_at')}（{tst.get('matches')}試合・ブック別 {tst.get('with_book')}試合）"),
           feed_duplicates_skipped=o["dup"], facts_written=112,
           blockers=["テニスの事実（直近成績・H2H）と独立モデル（Tennis Abstract Elo）が取れない：tennisexplorer.com・tennisabstract.com がクラウドのプロキシで遮断（項目8〜10・14）",
                     "サッカー・バスケ・ホッケー・卓球・ダーツ・スヌーカー・バドミントン・クリケット・バレーは現行の独立モデルが見つからず②③④は判定不能（項目8〜10）",
                     "深掘り112件中89件は直近成績5試合未満（取得元の遮断・承認待ち）。ITF/UTR/Futuresのテニス約80件は深掘り枠外（項目12・14）",
                     "BET CHANNEL配信（VPS）が503で失敗、BET CHANNEL専用eスポーツ（KoG・MLBB・R6・CrossFire等）は前回値の引継ぎ（項目5）",
                     "結果未公表の既存カード2件（Bestia Academy-QUINTESSENCIA・Virtus.pro-BOGATYRI）は次回確認（項目17）",
                     "odds-fetch の毎時スケジュールが間引かれている（06:40分が未実行）"],
           checklist=CL, checklist_notes=notes)
runs.append(run)
core.save("automation-runs.json", runs)
build()
print("ok", sum(CL.values()), "/41")
