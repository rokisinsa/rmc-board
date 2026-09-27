"""run-20260927-2300b の automation-runs 記録（41項目チェックリスト）。引数: 出力ディレクトリ(run_out.json の場所) start_sha"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core
from rmc.build import build

OUT, START_SHA = sys.argv[1], sys.argv[2]
o = json.load(open(os.path.join(OUT, "run_out.json"), encoding="utf-8"))
inv = core.load("snapshots/run-20260927-2300b/inventory.json")
runs = core.load("automation-runs.json")
prev = runs[-1]
CL = {f"{i:02d}": False for i in range(1, 42)}
for k in ("01", "07", "08", "09", "10", "11", "13", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
          "28", "29", "30", "31", "32", "33"):
    CL[k] = True
notes = {
    "01": "23:00枠。22:56 JST起動、start_sha記録。前回run-20260927-2345（別セッションの追加更新）はpartial→blockersを引き継ぎ。push競合のため最新mainに再適用",
    "02": "BET CHANNEL全メニュー未取得（クラウドから直接接続不可。直前のrun-20260927-2345はPC内蔵ブラウザ経由で721件取得したが、本回はPC未接続）",
    "03": "カジ旅・遊雅堂はログイン必要で確認不能、bet365は記事掲載値のみ部分的",
    "04": "6系統のサブエージェントで走査。フィールドホッケー（アジア大会）4試合を追加。ダーツMODUS残り4試合は開始時刻取れず未登録。betexplorer/oddsportal/Liquipedia/HLTVで取得失敗（承認タイムアウト・429）が多く網羅性は不完全",
    "05": "eスポーツはCS2/LoL/Dota2/R6のみ確認。VALORANT Champions・HoK/OW2/RL/CoD/PUBG/MLBB/SC2/EA FC/eBasketball等は時間切れで未走査",
    "06": "競技別件数は記録したが、走査が不完全なため件数自体が全数と言えない",
    "11": "競技内でロジック別に判定・深掘り対象を選定（競技横断の上位抽出なし）",
    "12": "Dota 2・ラグビー・ラグビーリーグ・Rainbow Six（価格なし）は本回の新規深掘りなし（前回深掘り継続またはwaiver記録）。VALORANTは掲載0件",
    "14": "深掘り27件。H2H・フォーム・単一ブック値・独立モデルが unavailable の項目が多い",
    "15": "eスポーツ深掘りは CS2 1件・LoL 1件のみ。map pool/veto/patch の多くが unavailable",
    "16": "本回の新規正式採用0件（条件を満たす候補なし。無理な採用はしない）",
    "17": "既存正式カード16件（①15・③1）はすべて開始前（最早 9/28 00:30）で pending。開始済み未確定カードなし",
    "18": "結果確定対象なし（開始済みカードなし）", "19": "結果確定対象なし", "21": "精算対象なし",
    "26": "旧移行カードなし", "27": "敗戦カードなし",
    "34": "commit/push後に確認", "35": "push後に確認", "36": "push後に確認", "37": "push後に確認",
    "38": "push後に確認", "39": "push後に確認", "40": "報告送信後に確定", "41": "上記未完了があるため定時更新完了とはしない",
}
run = dict(run_id="run-20260927-2300b", slot="23:00", started_at="2026-09-27T22:56:05+09:00", finished_at=core.now_jst(),
           start_sha=START_SHA, status="partial", previous_run_ok=False, carried_blockers=prev.get("blockers", []),
           inventory_match_ids=inv, coverage=o["coverage"], sports_disappeared=o["gone"],
           sources=dict(betchannel="確認不能：クラウドから直接接続不可（run-20260927-2345ではPCの内蔵ブラウザ経由で取得。本回はPC未接続のため公開オッズサイト中心）",
                        kajitabi="確認不能：ログインが必要", bet365="一部取得：記事掲載のbet365値（デンマーク戦・ノルウェー戦・韓国戦・ボンジ戦・ハンブルク戦）",
                        yuugado="確認不能：ログインが必要", scan_notes=o["scan"]),
           blockers=["BET CHANNELの全メニュー取得ができない（項目2）",
                     "カジ旅・遊雅堂は確認不能（項目3）",
                     "betexplorer/oddsportal/Liquipedia/HLTVへの取得失敗が多く、走査の網羅性が不完全（項目4〜6）。ダーツMODUS残り4試合未登録",
                     "eスポーツはCS2/LoL/Dota2/R6以外のタイトルを時間内に走査できず（項目5）",
                     "深掘りの多くで単一ブックの現在値・独立モデルが取れず正式採用なし。Dota2・ラグビー系は新規深掘りなし（項目12・14・15）",
                     "Actions・Pages・公開値の確認はpush後（項目34〜39）"],
           checklist=CL, checklist_notes=notes)
runs.append(run)
core.save("automation-runs.json", runs)
build()
print("ok", sum(CL.values()), "/41")
