# RMC 定時更新 手順書

定時更新（06:00／12:00／18:00／23:00 JST）を実行するセッションは、この手順書と `CHECKLIST.md` を最初に読む。
チェックリスト41項目の結果は必ず run に記録し、1つでも未完了なら `status` を `complete` にしない。

## データ構成（すべて `data/` 配下・JSTは `YYYY-MM-DDTHH:MM:SS+09:00`）

| ファイル | 中身 | 書き換え |
|---|---|---|
| `matches.json` | `{match_id: {sport, competition, round, start_jst, left, right, home_away, status, result, note, flags}}`。status は scheduled / live / final / postponed / cancelled / abandoned / unknown / review_required | 追記・状態更新のみ |
| `odds_snapshots.json` | `[{match_id, taken_at, source, market, prices{L,D,R}, exact, book_verified}]` | 追記のみ |
| `analysis/r1〜r4.json` | その回の全件判定 `{logic, run_id, run_started_at, rows:[{match_id, status, reason, deep_dive, deep_dive_detail, priced, …指標}]}` | 毎回まるごと作り直す（前回分は `snapshots/` に保存） |
| `ledger/r1〜r4.json`, `ledger/experience.json` | 正式採用の台帳 `[{entry_id, match_id, market, selection, selection_key(L/D/R), odds_taken, stake, locked_at, odds_source, prior_prob, result}]` | **append-only**。既存行は `result` を null→値 にする以外変更禁止 |
| `automation-runs.json` | run記録 `[{run_id, slot, started_at, finished_at, start_sha, end_sha, status, previous_run_ok, carried_blockers, inventory_match_ids, coverage, sources, blockers, checklist, checklist_notes, sports_disappeared}]` | 追記のみ |
| `summary.json` | `python -m rmc.build` が台帳から生成。手で書かない | 生成のみ |
| `snapshots/<run_id>/` | 各回の analysis と inventory の控え | 作成後は不変 |

判定値：①は accepted/watch/rejected/nodata、②は formal/conditional/watch/excluded/nodata、③は adopted/watch/excluded/nodata、④は accepted/watch/rejected/nodata。

## 1回の流れ

1. **起動確認（項目1）**：`git pull`、`git rev-parse HEAD` を start_sha に記録。前回runの status と blockers を読み、未解決分を `carried_blockers` に引き継ぐ。
2. **インベントリ（項目2〜6）**：BET CHANNEL を基準に全メニューを取得（取得できなければ `sources.betchannel` に「確認不能：理由」）。カジ旅・bet365・遊雅堂も同様に記録。今後24時間の試合を全競技・全eスポーツタイトルで集め、`matches.json` と `odds_snapshots.json` に追記。競技別に event_count / priced_upcoming_count / market_count を数える。前回あった競技が消えたら `sports_disappeared` に理由。
3. **①〜④の全件独立走査（項目7〜13, 28, 29）**：4ロジックそれぞれが inventory の全 match_id を1行ずつ判定する。他ロジックの推定・理由を流用しない。競技ごとに（全競技横並びの上位抽出は禁止）各ロジック最低1件、試合数が多い競技は上位3件程度を deep_dive。deep_dive しない場合は理由を `deep_dive_waiver` に書く。
4. **deep_dive（項目14, 15）**：`rmc/validate.py` の `DEEP_FIELDS_COMMON`（eスポーツは `DEEP_FIELDS_ESPORTS` も）をすべて埋める。取れない項目は `{"unavailable": true, "reason": "…"}`。`data_as_of` は走査開始時刻より前。
5. **正式採用（項目16, 20）**：条件を満たすものは件数上限なしで ledger に追記。exact odds・stake($100)・locked_at（試合開始前）必須。レンジしかなければ正式採用しない。
6. **結果更新（項目17〜21）**：全ledgerの開始済み未確定カードを確認。公式→リーグ公式→結果DB→ライブスコアの順でソースを取り、`result.source_rank` と `identity_checked` を付けて matches を更新。同じ match_id の全ロジック・経験値取引へ精算を反映。
7. **集計・post-match review（項目22〜27）**：`python -m rmc.build`。敗戦カードは `reviews/<entry_id>.md` に事前仮説・結果・見落とし・variance/structural 判定を書く。
8. **検証・反映（項目32〜35）**：`python -m unittest discover -s tests -t .` → `python -m rmc.validate --base HEAD` → commit → push（競合時は pull --rebase して 3〜7 のデータを再適用し、テストを最初から）→ end_sha を記録。GitHub Actions の結果を確認。
9. **公開確認（項目36〜39）**：Pages の `index.html` と `data/summary.json`・`data/deploy.json` を cache bust 付きで取得し、run_id と SHA が最新か、公開JSONから再計算した収支が一致するかを確認。
10. **報告（項目40, 41）**：全カテゴリ数・イベント数・市場数、競技別の走査→深掘り→正式/watch/除外、新規正式採用・watch全件、結果更新全件、①〜④と経験値取引の戦績・投入・損益・ROI・未計算・pending・複利・1/4ケリー、SHA・Actions・Pages結果を報告する。

## コマンド

```
python -m unittest discover -s tests -t .   # テスト
python -m rmc.build                          # summary.json 再生成
python -m rmc.validate --base HEAD~1         # 検証（locked保護を含む）
```
