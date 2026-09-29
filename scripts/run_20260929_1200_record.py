"""run-20260929-1200 の automation-runs 記録（41項目チェックリスト）。使い方: python scripts/run_20260929_0600_record.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core
from rmc.build import build

RUN_ID = "run-20260929-1200"
o = json.load(open("/home/claude/dd/run_out.json", encoding="utf-8"))
inv = core.load(f"snapshots/{RUN_ID}/inventory.json")
bst = core.load("odds_feed/status.json"); tst = core.load("odds_feed/tennis_status.json"); bcs = core.load("bc/feed/status.json", {})
runs = core.load("automation-runs.json")
prev = runs[-1]
CL = {f"{i:02d}": False for i in range(1, 42)}
for k in ("01", "02", "03", "06", "07", "08", "09", "10", "11", "13", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
          "28", "29", "30", "31", "32", "33"):
    CL[k] = True
gone = {sp: "今回の公開配信（Bovada 11:56）に24時間以内の未開始試合なし（前回分は開始済み）" for sp in o["gone"]}
nfacts = len(__import__("glob").glob("/home/claude/dd/out/*.json"))
notes = {
    "01": "12:00枠。11:56 JST起動、start_sha c01f5e4。前回 run-20260929-0600 は partial → blockers を carried_blockers に引継ぎ（結果未公表2件は今回確認）",
    "02": f"読み替え表の方法：odds-fetch を workflow_dispatch で再取得し、公開配信 Bovada {bst.get('taken_at')}（{bst.get('events')}件・価格あり{bst.get('priced')}件、全21カテゴリ中取得失敗1＝水球404）・tennisexplorer {tst.get('taken_at')}（{tst.get('matches')}試合・ブック別{tst.get('with_book')}）を基準インベントリにした。重複は feed_id と名前照合（汎用語除外）で確認し誤対応0。BET CHANNEL配信（VPS）は {bcs.get('taken_at')} の HTTP 503 のまま",
    "03": "読み替え表の方法：カジ旅・遊雅堂（ログイン必要）・bet365直接（クラウド不可）は sources に確認不能と理由を記録。テニスは tennisexplorer 経由のブック別値を external_market に保存",
    "04": "Bovada・tennisexplorer 掲載の全競技（サッカー・テニス・ホッケー・バスケ・野球・卓球・ダーツ・スヌーカー・クリケット・バレー）を全件走査。ハンド・ラグビー・ボクシング・フットサルは配信0件、水球は404。深掘りは全件には届かず（項目12・14参照）",
    "05": "eスポーツは Bovada 掲載（CS2・Dota 2・VALORANT・LoL）24時間以内・価格あり16試合を全件深掘り。BET CHANNEL専用タイトル（KoG・MLBB・R6・CrossFire・SC:BW）は配信503のため前回値・前回判定の引継ぎ",
    "06": "競技別に event_count／priced_upcoming_count／market_count を coverage に記録。消えた競技（アメフト・バドミントン）は sports_disappeared に理由",
    "09": "読み替え表の方法：CLV・締切前オッズ・calibration・オッズ帯ROIは build が summary.analytics に自動計算",
    "10": "読み替え表の方法：同上（opening／closing／CLV）",
    "11": "競技ごとにサブエージェントが競技内で候補を選定（競技横断の上位抽出なし）",
    "12": f"今回の新規・追補深掘り{nfacts}件（テニス22・サッカー11・ホッケー7・野球3・バスケ6・バレー4・クリケット1・卓球9・スヌーカー4・ダーツ1・eスポーツ16）。24時間以内・価格あり約730試合の全件には届かず（サブエージェント共通のWeb検索上限200回に到達）",
    "14": "深掘りのうちスヌーカー・eスポーツ・ATP/Challenger/ITFの一部・ホッケー（NHL・チェコ・スイス）は両者5試合以上。サッカー（ページ取得不可で検索見出しのみ）・卓球・一部バスケは事実が薄く、事実不足ガードで①でも正式採用しない。記憶由来のH2H行は削除",
    "15": "eスポーツ16件で format・LAN/online・roster・map pool・veto・patch・series/map H2H・rating を記録（veto・確定mapは未発表で unavailable）",
    "16": "新規正式採用は①13件（条件を満たす全件：スヌーカー3・テニス8・ホッケー2）。②③④は独立モデル（Dimers）が取れた試合でも基準未達で watch/除外（無理な採用なし）",
    "17": "開始済み未確定の正式カード4件を全件確認：確定3件（Cuba・Marsborne・QUINTESSENCIA すべて勝ち）、Virtus.pro-BOGATYRI は結果未公表で result_pending_reason を更新",
    "18": "CONCACAF公式（リーグ公式）・Mais Esports／draft5（結果DB）で確定。スニペットのみの確定なし",
    "19": "日付・JST時刻・大会・ラウンド・相手を identity_note に記録（Bestia-QUINTESSENCIA は表示時刻の1時間差を同日唯一の対戦として照合）",
    "21": "同じ match_id の全ロジック・経験値取引へ反映",
    "27": "今回の確定は3勝0敗で敗戦なし（post-match review の新規対象なし）",
    "34": "commit/push後に確認", "35": "push後に確認", "36": "push後に確認", "37": "push後に確認",
    "38": "push後に確認", "39": "push後に確認", "40": "報告送信後に確定", "41": "上記未完了があるため定時更新完了とはしない",
}
run = dict(run_id=RUN_ID, slot="12:00", started_at="2026-09-29T11:56:18+09:00", finished_at=core.now_jst(),
           start_sha="c01f5e4", status="partial", previous_run_ok=False, carried_blockers=prev.get("blockers", []),
           inventory_match_ids=inv["match_ids"], coverage=o["coverage"], sports_disappeared=gone,
           sources=dict(betchannel=f"確認不能：VPS配信 data/bc/feed が {bcs.get('taken_at')} に HTTP 503 で失敗したまま、クラウドからは直接接続できない（ユーザー指示によりBovada等の公開配信で代替）",
                        kajitabi="確認不能：ログインが必要（クラウドから接続不可）",
                        bet365="確認不能（直接）：クラウドから接続不可。テニスのみ tennisexplorer 経由で bet365 値を取得",
                        yuugado="確認不能：ログインが必要（クラウドから接続不可）",
                        bovada=f"取得：公開coupon JSON {bst.get('taken_at')}（{bst.get('events')}件・odds-fetch を workflow_dispatch で再取得）",
                        tennisexplorer=f"取得：{tst.get('taken_at')}（{tst.get('matches')}試合・ブック別 {tst.get('with_book')}試合）"),
           feed_duplicates_skipped=o["dup"], facts_written=nfacts,
           blockers=["深掘りが24時間以内・価格あり約730試合の全件に届かない：サブエージェント共通のWeb検索上限（200回）に到達、WebFetchは検索結果に出たURL以外を開けない（項目4・12・14）",
                     "サッカーの深掘りは結果ページを開けず検索見出しのみ・独立モデルなし（項目8〜10・14）",
                     "テニスの Tennis Abstract Elo はJS描画で取得できず、独立モデルはDimers（ATP主要大会のみ）。tennisexplorer・sofascoreはプロキシで遮断（項目8〜10・14）",
                     "サッカー・バスケ・KHL/欧州ホッケー・卓球・ダーツ・スヌーカー・クリケット・バレーは現行の独立モデルが見つからず②③④は判定不能（項目8〜10）",
                     "BET CHANNEL配信（VPS）が503のまま、BET CHANNEL専用eスポーツ（KoG・MLBB・R6・CrossFire等）は前回値の引継ぎ（項目5）",
                     "結果未公表の既存カード1件（Virtus.pro-BOGATYRI、Mir Tankov）は次回確認"],
           checklist=CL, checklist_notes=notes)
runs.append(run)
core.save("automation-runs.json", runs)
build()
print("ok", sum(CL.values()), "/41")
