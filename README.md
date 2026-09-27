# RMC 分析ボード

①推奨取引・②VALUE①・③VALUE②・④PRO EDGE の4ロジックを独立に走らせ、24時間以内の全試合を 正式採用／watch／除外／データ不足 に振り分けて公開する静的サイト（GitHub Pages）。

- 画面：`index.html`（`data/*.json` を読むだけ）
- 更新手順：`RUNBOOK.md`
- 完了条件：`CHECKLIST.md`（41項目。1つでも未完了なら完全更新扱いにしない）
- 検証：`rmc/validate.py`（GitHub Actions で push ごとに実行。失敗すると Pages に出ない）
