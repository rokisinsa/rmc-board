"""run-20260928-0600 の automation-runs 記録（41項目チェックリスト）。引数: finished_at なし（現在時刻）"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core
from rmc.build import build

RUN_ID = "run-20260928-0600"
o = json.load(open("/home/claude/dd/run_out.json", encoding="utf-8"))
inv = core.load(f"snapshots/{RUN_ID}/inventory.json")
bst = core.load("odds_feed/status.json"); tst = core.load("odds_feed/tennis_status.json")
runs = core.load("automation-runs.json")
prev = runs[-1]
CL = {f"{i:02d}": False for i in range(1, 42)}
for k in ("01", "06", "07", "08", "09", "10", "11", "13", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
          "28", "29", "30", "31", "32", "33"):
    CL[k] = True
notes = {
    "01": "06:00枠。05:55 JST起動、start_sha 5b513ac。前回run-20260928-0030はpartial→blockersを引継ぎ。05:40の定時odds-fetchが未実行だったためworkflow_dispatchで再取得（Bovada 05:56／tennisexplorer 05:59）",
    "02": "BET CHANNEL：クラウドから接続不可（JS描画・VPS配信 data/bc/feed も未更新）で確認不能",
    "03": "カジ旅・遊雅堂はログイン必要、bet365直接はクラウド不可で確認不能。テニスは tennisexplorer 経由で bet365/Pinnacle/1xBet 等のブック別値をクロスチェック（external_market）",
    "04": f"公開配信の全カテゴリ（Bovada {bst.get('events')}件・tennisexplorer {tst.get('matches')}試合）から今後24時間を取り込み。Bovadaに掲載のない競技（ハンドボール・水球・フィールドホッケー・アジア大会バレー・卓球・ラグビー・格闘技・モータースポーツ）は前回登録分の引継ぎのみで新規走査なし",
    "05": "eスポーツは公開配信に24時間以内の掲載があった CS2・LoL・Rainbow Six を全件判定。BET CHANNEL掲載タイトル（VALORANT・Dota 2・KoG・CrossFire・WoT・MLBB等）は前回登録分の引継ぎのみ",
    "06": "競技別に event_count／priced_upcoming_count／market_count を記録（coverage）",
    "11": "競技ごとにサブエージェントが①用・②③④用の候補を競技内で選定（競技横断の上位抽出なし）",
    "12": "Bovada未掲載の競技（ハンドボール・水球・ホッケー（フィールド）・卓球等）とダーツMODUSは深掘りなし（waiver記録）",
    "14": "深掘り55件。直近10試合・H2H・先発GK等が取れない項目は unavailable＋理由（数字の推測なし）",
    "15": "eスポーツ深掘り11件。LoLのpatch・R6のmap pool・veto の多くが unavailable",
    "16": "新規正式採用は①のみ（条件を満たす全件）。②③④は独立モデルが取れた試合でも基準未達のため0件（無理な採用なし）",
    "17": "既存正式カード34件の開始済み未確定分を全件確認。確定12件、試合中・未判明4件（レンジャーズ-ツインズ、カーディナルス-49ers、Galorys-Procyon、GHOST SQUAD-PARADOX）は次回再確認",
    "18": "結果DB（flashscore・sofascore・ESPN・CBS）とチーム公式（Jets・Bills）で確定。スニペットのみの確定なし",
    "19": "日付・JST時刻・大会・相手・H/Aを確認（identity_note 記録）",
    "21": "同じ match_id の全ロジック・経験値取引へ反映",
    "27": "①の敗戦4件（ツェリェ・ドランメン・シーホークス・リンクス）を data/reviews/ に記録（1敗で係数は変えない）",
    "34": "commit/push後に確認", "35": "push後に確認", "36": "push後に確認", "37": "push後に確認",
    "38": "push後に確認", "39": "push後に確認", "40": "報告送信後に確定", "41": "上記未完了があるため定時更新完了とはしない",
}
run = dict(run_id=RUN_ID, slot="06:00", started_at="2026-09-28T05:55:27+09:00", finished_at=core.now_jst(),
           start_sha="5b513ac", status="partial", previous_run_ok=False, carried_blockers=prev.get("blockers", []),
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
                     "Bovada未掲載の競技（ハンドボール・水球・フィールドホッケー・アジア大会バレー・卓球・格闘技等）は新規走査なし（項目4・12）",
                     "eスポーツはBovada掲載のCS2・LoL・R6のみ新規判定。VALORANT等は前回分の引継ぎ（項目5）",
                     "サッカー・ホッケー・ダーツ・スヌーカー・バドミントン・クリケット・NPBは直前の独立モデルが取れず②③④は判定不能（項目8〜10・14）",
                     "試合中・結果未判明の既存カード4件は次回確認（項目17）",
                     "Actions・Pages・公開値の確認はpush後（項目34〜39）"],
           checklist=CL, checklist_notes=notes)
runs.append(run)
core.save("automation-runs.json", runs)
build()
print("ok", sum(CL.values()), "/41")
