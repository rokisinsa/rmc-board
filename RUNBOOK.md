# RMC 定時更新 手順書

定時更新（06:00／12:00／18:00／23:00 JST）を実行するセッションは、この手順書と `CHECKLIST.md` を最初に読む。
チェックリスト41項目の結果は必ず run に記録し、1つでも未完了なら `status` を `complete` にしない。

## データ構成（すべて `data/` 配下・JSTは `YYYY-MM-DDTHH:MM:SS+09:00`）

| ファイル | 中身 | 書き換え |
|---|---|---|
| `matches.json` | `{match_id: {sport, competition, round, start_jst, left, right, home_away, status, result, note, flags}}`。status は scheduled / live / final / postponed / cancelled / abandoned / unknown / review_required | 追記・状態更新のみ |
| `odds_snapshots.json` | `[{match_id, taken_at, source, market, prices{L,D,R}, exact, book_verified}]` | 追記のみ |
| `analysis/r1〜r4.json` | その回の全件判定 `{logic, run_id, run_started_at, decided_at（判定・ロック時刻。deep_dive の data_as_of はこれ以前）, rows:[{match_id, status, reason, deep_dive, deep_dive_detail, priced, …指標}]}` | 毎回まるごと作り直す（前回分は `snapshots/` に保存） |
| `ledger/r1〜r4.json`, `ledger/experience.json`（2026-09-29開始の試合から。以前の分は `ledger_archive/` に保管・集計対象外） | 正式採用の台帳 `[{entry_id, match_id, market, selection, selection_key(L/D/R), odds_taken, stake, locked_at, odds_source, prior_prob, result}]` | **append-only**。既存行は `result` を null→値 にする以外変更禁止 |
| `automation-runs.json` | run記録 `[{run_id, slot, started_at, finished_at, start_sha, end_sha, status, previous_run_ok, carried_blockers, inventory_match_ids, coverage, sources, blockers, checklist, checklist_notes, sports_disappeared}]` | 追記のみ |
| `facts/<match_id>.json` | 深掘りした試合の事実を日本語で構造化（両チームの直近成績・H2Hを1試合1行のリスト、メンバー、会場、リスク、不足）。形は `docs/FACTS_SPEC.md`。画面の縦リスト表示はこれを読む | 深掘りのたびに作成・更新 |
| `summary.json` | `python -m rmc.build` が台帳から生成。手で書かない | 生成のみ |
| `snapshots/<run_id>/` | 各回の analysis と inventory の控え | 作成後は不変 |

判定値：①は accepted/watch/rejected/nodata、②は formal/conditional/watch/excluded/nodata、③は adopted/watch/excluded/nodata、④は accepted/watch/rejected/nodata。

## 1回の流れ

1. **起動確認（項目1）**：`git pull`、`git rev-parse HEAD` を start_sha に記録。前回runの status と blockers を読み、未解決分を `carried_blockers` に引き継ぐ。
2. **インベントリ（項目2〜6）**：BET CHANNEL を基準に全メニューを取得（取得できなければ `sources.betchannel` に「確認不能：理由」）。カジ旅・bet365・遊雅堂も同様に記録。今後24時間の試合を全競技・全eスポーツタイトルで集め、`matches.json` と `odds_snapshots.json` に追記。競技別に event_count / priced_upcoming_count / market_count を数える。前回あった競技が消えたら `sports_disappeared` に理由。
   - **PCオフでの実オッズ（優先）**：GitHub Actions `odds-fetch` が JST 05:40／11:40／17:40／22:40 に公開オッズ配信（Bovada）を取り、`data/odds_feed/bovada.json` に保存している（`status.json` で取得件数と時刻を確認）。定時更新はまず `git pull` してこれを使う。1試合＝1ブックの exact odds として `odds_snapshots` に `source: "Bovada（公開coupon JSON・<取得時刻>取得）"` で追記し、①〜④の判定・正式採用に使ってよい。チーム名は英語なので、`rmc/oddsfeed.py` の `match()` で自動対応づけし、日本語名の試合は開始時刻と大会で目視対応づけする。
   - **テニス**：同じ odds-fetch が tennisexplorer から今日・明日の全試合とブック別オッズを `data/odds_feed/tennis.json` に保存している（`tennis_status.json` で件数確認）。各試合の `pick`（bet365＞Pinnacle＞1xBet…の順で最初にあるブック）を単一ブックの exact odds として使い、`source` にブック名と「tennisexplorer経由」を書く。
   - **BET CHANNELの取得元**：`data/bc/feed/status.json` が ok かつ `taken_at` が1時間以内なら `data/bc/feed/latest.json`（`scripts/bc_fetch.py` が日本のVPS等から保存した配信）を使う。古い・失敗なら PC の内蔵ブラウザで取得し、どちらも無理なら `sources.betchannel` に「確認不能：理由」。
   - **eスポーツは全タイトル必須**：BET CHANNEL の LIVEスポーツ prematch配信（sptpub）から eスポーツ（CS2・LoL・Dota 2・VALORANT・R6・World of Tanks・CrossFire・King of Glory・Mobile Legends・StarCraft BW・Fortnite）とシミュレーション系（FC 26・NBA 2K26・eサッカー・eバスケ・eテニス・V-クリケット等）を全件取り、`data/bc/<取得時刻>-esports.txt` に控えを残す（形式は `rmc/bcfeed.py`）。
   - 既存の略称行（LoL EMEA Masters の TLNP など）は `rmc/bcmap.py` の KNOWN で BET CHANNEL の event に対応づけ、重複登録しない。取り込み・判定の手順は `scripts/run_20260928_0030_esports.py` を雛形にする。
   - シミュレーション系は実力データがないため①の一次判定のみ（正式採用しない）。**実チーム系は「24時間以内・価格あり」の全試合を deep_dive 必須**（各ロジック1件ではなく全件。取り切れない場合は blockers に残数と理由。既に facts が徹底水準にある試合は直近結果の追記だけでよい）。独立勝率は外部モデルがなければ `rmc/model.py`（直近成績の log5）。**log5 での正式採用ガード：市場との乖離15pt超・モデル勝率が市場の1.6倍超・EVが②で+25%超／③で+20%超／④で+15%超のものは正式採用せず watch 止まり**（相手の強さ未補正の歪み対策）。tier-3常設リーグ（United21・European Pro League・EPIC等）は「下位リーグ（整合性リスク）」フラグで watch 止まり。
3. **①〜④の全件独立走査（項目7〜13, 28, 29）**：4ロジックそれぞれが inventory の全 match_id を1行ずつ判定する。他ロジックの推定・理由を流用しない。競技ごとに（全競技横並びの上位抽出は禁止）各ロジック最低1件、試合数が多い競技は上位3件程度を deep_dive。deep_dive しない場合は理由を `deep_dive_waiver` に書く。
4. **deep_dive（項目14, 15）— 事実は徹底取得**：正式採用・watch にする試合は、直近成績＝両者10試合（日付YYYY-MM-DD・スコア・units・detail必須）、H2H＝最大10件（年をまたいで全部。無ければ「初対戦」を確認した根拠）、共通の対戦相手＝60日以内の共通相手との全試合を left.history / right.history、まで埋める。1つのサイトで出なければ最低3系統（競技DB→Wikipedia→現地語ニュース。中国語・韓国語・ロシア語・スペイン語検索も使う）。取れないものだけ `unavailable` に理由。**未確定の正式採用カードがこの水準を満たさないと `rmc.validate` の FACTS_COVERAGE で止まる。** 前回までの未確定カードで facts が薄いもの（form5未満・h2h空・history空で理由なし）も毎回この水準まで追補する。
   元の手順：事実は `docs/FACTS_SPEC.md` の形で `data/facts/<match_id>.json` にも保存する（日本語・1試合1行）。`rmc/validate.py` の `DEEP_FIELDS_COMMON`（eスポーツは `DEEP_FIELDS_ESPORTS` も）をすべて埋める。取れない項目は `{"unavailable": true, "reason": "…"}`。`data_as_of` は走査開始時刻より前。
5. **正式採用（項目16, 20）— 全競技から①〜④それぞれ必ず出す（ユーザー指示 2026-09-29）**：通常基準を満たすものは上限なしで全部採用し、そのうえで通常基準の正式採用が1件もない競技（リアルスポーツ各種目・eスポーツ各タイトル）は `rmc.select.apply_floor(lg, rows, matches, ledger, LOCKED)` で競技内の最上位1件を「競技枠」（pick_type=sport_floor）として正式採用する。analysis には `floor_applied_at` を記録。validate の SPORT_FLOOR が強制。競技枠の最低条件（深掘り済み・両者に実績あり・exact odds・24時間以内・シミュ/ショーマッチ等でない・②③④は独立勝率あり、市場との差15pt以内・オッズ4.0以下を優先）は rmc/select.py の冒頭。収支は通常基準／競技枠の内訳も summary.by_type に出る。**判定（ロック）時刻から24時間以内に始まる試合だけ**（`core.within_horizon`。24時間より先は基準を満たしても watch「24時間超」で、次回以降の定時更新で再判定。validate の FORMAL_HORIZON が強制）。entry_id は `core.next_entry_id`（取消済みがあれば枝番）。条件を満たすものは件数上限なしで ledger に追記。exact odds・stake($100)・locked_at（試合開始前）必須。レンジしかなければ正式採用しない。
6. **結果更新（項目17〜21）— 毎回必須・最優先**：開始から4時間を過ぎた未精算の正式採用が1件でも残っていると `rmc.validate` の RESULT_OVERDUE で止まる（延期・結果未公表など本当に確定できないときだけ matches の `result_pending_reason` に理由）。深掘りより先にサブエージェントで全件の結果を確認して精算する。全ledgerの開始済み未確定カードを確認。公式→リーグ公式→結果DB→ライブスコアの順でソースを取り、`result.source_rank` と `identity_checked` を付けて matches を更新。同じ match_id の全ロジック・経験値取引へ精算を反映。
7. **集計・post-match review（項目22〜27）**：`python -m rmc.build`（格差スコア帯別 70〜80／80〜90／90以上の単利収支 `summary.gap_bands` も自動再計算。単利＝毎回$100固定、複利＝元金$100全額・倍額$200到達で利益をストックし$100から再開・0になったら$100から再開、1/4ケリー）。敗戦カードは `reviews/<entry_id>.md` に事前仮説・結果・見落とし・variance/structural 判定を書く。
8. **検証・反映（項目32〜35）**：`python -m unittest discover -s tests -t .` → `python -m rmc.validate --base HEAD` → commit → push（競合時は pull --rebase して 3〜7 のデータを再適用し、テストを最初から）→ end_sha を記録。GitHub Actions の結果を確認。
9. **公開確認（項目36〜39）— 無人で完結**：push 後、`curl -s https://api.github.com/repos/rokisinsa/rmc-board/actions/runs?head_sha=<SHA>` で test-validate-deploy を探し、`/actions/runs/<id>/jobs` で **verify-public ジョブが success** なら 36〜39 を true（公開ファイル一致・公開JSONからの収支再計算一致・run_id一致をActionsが確認済み）。failure なら内容を blockers に書いて partial。以下は旧手順（参考）：WebFetch は15分キャッシュでクエリを無視することがあるため、SHA の確認は `data/deploys/<push したSHA>.json`（デプロイごとに新しいURL）を取得して行う。Pages の `index.html` と `data/summary.json`・`data/deploy.json` を cache bust 付きで取得し、run_id と SHA が最新か、公開JSONから再計算した収支が一致するかを確認。
10. **報告（項目40, 41）**：全カテゴリ数・イベント数・市場数、競技別の走査→深掘り→正式/watch/除外、新規正式採用・watch全件、結果更新全件、①〜④と経験値取引の戦績・投入・損益・ROI・未計算・pending・複利・1/4ケリー、SHA・Actions・Pages結果を報告する。

## コマンド

```
python -m unittest discover -s tests -t .   # テスト
python -m rmc.build                          # summary.json 再生成
python -m rmc.validate --base HEAD~1         # 検証（locked保護を含む）
```
