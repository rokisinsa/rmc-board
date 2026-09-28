"""run-20260928-1200 の automation-runs 記録（41項目チェックリスト）。"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core
from rmc.build import build

RUN_ID = "run-20260928-1200"
o = json.load(open("/home/claude/dd/run_out.json", encoding="utf-8"))
inv = core.load(f"snapshots/{RUN_ID}/inventory.json")
bst = core.load("odds_feed/status.json"); tst = core.load("odds_feed/tennis_status.json")
runs = core.load("automation-runs.json")
prev = runs[-1]
CL = {f"{i:02d}": False for i in range(1, 42)}
for k in ("01", "06", "07", "08", "09", "10", "11", "13", "16", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
          "28", "29", "30", "31", "32", "33"):
    CL[k] = True
notes = {
    "01": "12:00枠。11:55 JST起動、start_sha 6ead576。前回run-20260928-0600はpartial→blockersを引継ぎ。11:40の定時odds-fetchが未実行だったためworkflow_dispatchで再取得（Bovada 11:56／tennisexplorer 11:59、commit 094006b）",
    "02": "BET CHANNEL：クラウドから接続不可（JS描画・VPS配信 data/bc/feed も未更新）で確認不能",
    "03": "カジ旅・遊雅堂はログイン必要、bet365直接はクラウド不可で確認不能。テニスは tennisexplorer 経由で bet365/Pinnacle/1xBet 等のブック別値をクロスチェック（external_market）",
    "04": f"公開配信の全カテゴリ（Bovada {bst.get('events')}件・tennisexplorer {tst.get('matches')}試合）から今後24時間を取り込み（卓球58件を新規に走査）。Bovadaに掲載のない競技（ハンドボール・水球・フィールドホッケー・ラグビー・格闘技・モータースポーツ・アメフト）は前回登録分の引継ぎのみ。MLB・WNBAはシリーズ勝者市場のみで単一試合ではないため除外",
    "05": "eスポーツは公開配信に24時間以内の掲載があった CS2・LoL・Rainbow Six を全件判定・深掘り。BET CHANNEL掲載タイトル（VALORANT・Dota 2・KoG・CrossFire・MLBB・StarCraft BW）は前回登録分の引継ぎのみ",
    "06": "競技別に event_count／priced_upcoming_count／market_count を記録（coverage）",
    "11": "競技ごとにサブエージェントが①用・②③④用の候補を競技内で選定（競技横断の上位抽出なし）",
    "12": "Bovada未掲載の競技（ハンドボール・水球・フィールドホッケー）とBET CHANNEL専用のeスポーツ（24時間超）は今回の新規深掘りなし（前回判定の引継ぎ・waiver記録）",
    "14": "今回の新規深掘り31件（サッカー6・テニス8・バスケ1・野球2・ホッケー2・バレー2・クリケット1・ダーツ2・スヌーカー2・卓球1・eスポーツ4）。06:00深掘り分は判定を引継ぎ。テニスの直近成績はプロキシでtennisexplorer等が取得できず unavailable（数字の推測なし）",
    "15": "eスポーツ深掘り4件。magic-GamerLegion以外は直近成績が5シリーズ未満で内製log5は算出不可。R6・LoLのpatch・veto の多くが unavailable",
    "16": "新規正式採用は①3件（条件を満たす全件）。②③④は独立モデルが取れた試合（テニスElo5件・サッカーKickOff3件・CS2 log5 1件）でも基準未達またはリスク要因でwatch止まり（無理な採用なし）",
    "17": "既存正式カードの開始済み未確定分12件を全件確認。確定9件、ドロー変更で不成立2カード（void）、試合中2件（An Se-young-Chen Yufei・Sharipov-Honda）、結果未判明1件（GHOST SQUAD-PARADOX）は次回再確認",
    "18": "公式（USA Volleyball）・結果DB（HLTV・dust2.us・FOX Sports・AP配信）で確定。ドロー変更はATP公式ドローで確認。スニペットのみの確定なし",
    "19": "日付・JST時刻・大会・相手・H/Aを確認（identity_note 記録）。ポルトのテニス2カードは公式ドローで対戦不成立を確認、2カードは開始日を09-29に訂正",
    "21": "同じ match_id の全ロジック・経験値取引へ反映（プリズミッチ-リンコンは①②④すべて void）",
    "27": "①の敗戦2件（Feng/Huang・Galorys）を data/reviews/ に記録（1敗で係数は変えない）",
    "34": "commit/push後に確認", "35": "push後に確認", "36": "push後に確認", "37": "push後に確認",
    "38": "push後に確認", "39": "push後に確認", "40": "報告送信後に確定", "41": "上記未完了があるため定時更新完了とはしない",
}
run = dict(run_id=RUN_ID, slot="12:00", started_at="2026-09-28T11:55:32+09:00", finished_at=core.now_jst(),
           start_sha="6ead576", status="partial", previous_run_ok=False, carried_blockers=prev.get("blockers", []),
           inventory_match_ids=inv["match_ids"], coverage=o["coverage"], sports_disappeared=o["gone"],
           sources=dict(betchannel="確認不能：クラウドから接続できない（JavaScript描画。VPS配信 data/bc/feed も未更新）",
                        kajitabi="確認不能：ログインが必要（クラウドから接続不可）",
                        bet365="確認不能（直接）：クラウドから接続不可。テニスのみ tennisexplorer 経由で bet365 値を取得",
                        yuugado="確認不能：ログインが必要（クラウドから接続不可）",
                        bovada=f"取得：公開coupon JSON {bst.get('taken_at')}（{bst.get('events')}件、GitHub Actions odds-fetch を workflow_dispatch）",
                        tennisexplorer=f"取得：{tst.get('taken_at')}（{tst.get('matches')}試合・ブック別 {tst.get('with_book')}試合）"),
           feed_duplicates_skipped=o["dup"],
           blockers=["BET CHANNELの全メニュー取得ができない（項目2）",
                     "カジ旅・遊雅堂・bet365直接は確認不能（項目3）",
                     "Bovada未掲載の競技（ハンドボール・水球・フィールドホッケー・格闘技等）は新規走査なし（項目4・12）",
                     "eスポーツはBovada掲載のCS2・LoL・R6のみ新規判定。VALORANT等は前回分の引継ぎ（項目5）",
                     "サッカー（KickOff以外）・ホッケー・ダーツ・スヌーカー・バレー・クリケット・CPBL・卓球は独立モデルが取れず②③④は判定不能（項目8〜10・14）",
                     "試合中・結果未判明の既存カード3件（An Se-young-Chen Yufei・Sharipov-Honda・GHOST SQUAD-PARADOX）は次回確認（項目17）",
                     "Actions・Pages・公開値の確認はpush後（項目34〜39）"],
           checklist=CL, checklist_notes=notes)
runs.append(run)
core.save("automation-runs.json", runs)
build()
print("ok", sum(CL.values()), "/41")
