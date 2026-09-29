"""run-20260929-1800 の automation-runs 記録（41項目チェックリスト）。使い方: python scripts/run_20260929_0600_record.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core
from rmc.build import build

RUN_ID = "run-20260929-1800"
o = json.load(open("/home/claude/dd/run_out.json", encoding="utf-8"))
inv = core.load(f"snapshots/{RUN_ID}/inventory.json")
bst = core.load("odds_feed/status.json"); tst = core.load("odds_feed/tennis_status.json"); bcs = core.load("bc/feed/status.json", {})
runs = core.load("automation-runs.json")
prev = runs[-1]
CL = {f"{i:02d}": False for i in range(1, 42)}
for k in ("01", "02", "03", "06", "07", "08", "09", "10", "11", "13", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
          "28", "29", "30", "31", "32", "33"):
    CL[k] = True
gone = {sp: "今回の公開配信（Bovada 17:56）・BET CHANNEL引継ぎ分に24時間以内の未開始試合なし（前回分は開始済み）" for sp in o["gone"]}
nfacts = len(__import__("glob").glob("/home/claude/dd/out/*.json"))
LOCK = open("/home/claude/dd/lock.txt").read().strip()
notes = {
    "01": f"18:00枠。17:55 JST起動、start_sha 23cc76f。前回 run-20260929-1200 は partial → blockers を carried_blockers に引継ぎ（結果未公表だった Virtus.pro-BOGATYRI は今回確定）。判定ロック {LOCK}",
    "02": f"読み替え表の方法：配信が1.5時間前（16:29）だったため odds-fetch を workflow_dispatch で再取得し、公開配信 Bovada {bst.get('taken_at')}（{bst.get('events')}件・価格あり{bst.get('priced')}件、全21カテゴリ中取得失敗1＝水球404）・tennisexplorer {tst.get('taken_at')}（{tst.get('matches')}試合・ブック別{tst.get('with_book')}）を基準インベントリにした。重複は feed_id と名前照合で確認（重複0）。BET CHANNEL配信（VPS）は {bcs.get('taken_at')} の失敗のまま",
    "03": "読み替え表の方法：カジ旅・遊雅堂（ログイン必要）・bet365直接（クラウド不可）は sources に確認不能と理由を記録。テニスは tennisexplorer 経由のブック別値を external_market に保存",
    "04": "Bovada・tennisexplorer 掲載の全競技（テニス・サッカー・卓球・ホッケー・バスケ・野球・ダーツ・スヌーカー・クリケット・バレー）を①〜④で全件走査。ハンド・ラグビー・ボクシング・フットサルは配信0件、水球は404。深掘りは全件には届かず（項目12・14参照）",
    "05": "eスポーツは Bovada 掲載（CS2・LoL・Dota 2・VALORANT・Rainbow Six）24時間以内・価格あり25試合を全件深掘り。BET CHANNEL専用タイトル（KoG・MLBB・CrossFire・R6の一部）は配信停止のため前回値・前回判定の引継ぎ",
    "06": "競技別に event_count／priced_upcoming_count／market_count を coverage に記録。消えた競技（StarCraft: BW）は sports_disappeared に理由",
    "09": "読み替え表の方法：CLV・締切前オッズ・calibration・オッズ帯ROIは build が summary.analytics に自動計算",
    "10": "読み替え表の方法：同上（opening／closing／CLV）",
    "11": "競技ごとにサブエージェントが競技内で候補を選定（①格差70以上の候補＋事実が薄い既存候補＋eスポーツ全件、競技横断の上位抽出なし）",
    "12": f"今回の新規・追補深掘り{nfacts}件（テニス101・バスケ20・サッカー12・CS2 11・ホッケー10・LoL 7・ダーツ8・卓球4・Dota 2 4・スヌーカー3・野球4・クリケット3・VALORANT 2・R6 1）。24時間以内・価格あり約820試合の全件には届かず",
    "14": "深掘りのうちMLB・Ligue Magnus・主要eスポーツ・一部テニス/サッカー代表戦は両者5試合以上。テニス下部大会（WebFetch不可・tennisexplorer/sofascore遮断で約70試合が0件）・バスケ（開幕直後）・卓球・クリケットは事実が薄く、事実不足ガードで①でも正式採用しない",
    "15": "eスポーツ25件で format・LAN/online・roster・map pool・veto・patch・series/map H2H・rating を記録（veto・確定mapは未発表で unavailable）",
    "16": "新規正式採用は①8件（条件を満たす全件：サッカー1・テニス3・バスケ1・ホッケー3）。②③④は独立モデル（Dimers MLB・Opta）が取れた試合でも基準未達で watch/除外（無理な採用なし）",
    "17": "開始済み未確定の正式カード3件を全件確認：確定1件（Virtus.pro 4-2 BOGATYRI 勝ち）、深圳オープンの Selby-Higginson・Wu Yize-Clarke は結果未公表で result_pending_reason を記録。Galfi-Micic（18:00開始）は進行中で次回確認",
    "18": "cybersport.ru（結果DB・大会記事とチームページの2系統）で確定。スニペットのみの確定なし",
    "19": "日付・JST時刻・大会・ラウンド・相手を identity_note に記録（Virtus.pro-BOGATYRI はグループ内唯一の対戦として照合、チームページの表示時刻差を注記）",
    "21": "同じ match_id の全ロジック・経験値取引へ反映",
    "27": "今回の確定は1勝0敗で敗戦なし（post-match review の新規対象なし）",
    "34": "commit/push後に確認", "35": "push後に確認", "36": "push後に確認", "37": "push後に確認",
    "38": "push後に確認", "39": "push後に確認", "40": "報告送信後に確定", "41": "上記未完了があるため定時更新完了とはしない",
}
run = dict(run_id=RUN_ID, slot="18:00", started_at="2026-09-29T17:55:43+09:00", finished_at=core.now_jst(),
           start_sha="23cc76f", status="partial", previous_run_ok=False, carried_blockers=prev.get("blockers", []),
           inventory_match_ids=inv["match_ids"], coverage=o["coverage"], sports_disappeared=gone,
           sources=dict(betchannel=f"確認不能：VPS配信 data/bc/feed が {bcs.get('taken_at')} に失敗したまま、クラウドからは直接接続できない（ユーザー指示によりBovada等の公開配信で代替）",
                        kajitabi="確認不能：ログインが必要（クラウドから接続不可）",
                        bet365="確認不能（直接）：クラウドから接続不可。テニスのみ tennisexplorer 経由で bet365 値を取得",
                        yuugado="確認不能：ログインが必要（クラウドから接続不可）",
                        bovada=f"取得：公開coupon JSON {bst.get('taken_at')}（{bst.get('events')}件・odds-fetch を workflow_dispatch で再取得）",
                        tennisexplorer=f"取得：{tst.get('taken_at')}（{tst.get('matches')}試合・ブック別 {tst.get('with_book')}試合）"),
           feed_duplicates_skipped=o["dup"], facts_written=nfacts,
           blockers=["深掘りが24時間以内・価格あり約820試合の全件に届かない：WebFetchは検索結果に出たURL以外を開けず（承認待ちで失敗する回もあり）、tennisexplorer・sofascore・flashscore・ITFはプロキシ遮断またはJS描画（項目4・12・14）",
                     "テニス下部大会・バスケ・卓球・クリケットは事実が薄い（0〜3試合）ものが多く、事実不足ガードで①でも正式採用しない（項目14）",
                     "独立モデルは Dimers（MLB）・Opta（代表戦1件）のみ。テニス（Tennis Abstract遮断）・サッカー・バスケ・欧州ホッケー・卓球・ダーツ・スヌーカー・クリケットは現行の独立モデルが見つからず②③④は判定不能（項目8〜10）",
                     "BET CHANNEL配信（VPS）が失敗のまま、BET CHANNEL専用eスポーツ（KoG・MLBB・CrossFire等）は前回値の引継ぎ（項目5）",
                     "結果未公表の既存カード2件（深圳オープン Selby-Higginson・Wu Yize-Clarke）と進行中1件（Galfi-Micic）は次回確認"],
           checklist=CL, checklist_notes=notes)
runs.append(run)
core.save("automation-runs.json", runs)
build()
print("ok", sum(CL.values()), "/41")
