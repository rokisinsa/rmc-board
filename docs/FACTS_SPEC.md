# 事実の構造化 v2（日本語・1試合1ファイル）— Web調査して埋める
現在時刻は current_time ツールで確認し data_as_of に書く。試合開始前の情報だけを使う。
数字を作らない・推測しない。見つからないものは入れずに unavailable に理由。件数が足りなければ見つかった分だけ入れて理由を書く。
出力先: data/facts/<match_id>.json（既存があれば上書き）。書いたら python で json.load して確認。

{
 "match_id": "...",
 "data_as_of": "YYYY-MM-DDTHH:MM:00+09:00",
 "unit": "セット|マップ|フレーム|レッグ|ゲーム|なし",   // 競技の勝敗単位（サッカー・バスケ・野球・アメフト・ホッケー・ハンド・ラグビー・クリケットは "なし"）
 "left":  {
   "name": "日本語名", "ranking": "世界ランク／リーグ順位／勝敗など1行",
   "form": [  // 直近10試合（公式戦優先、新しい順）。10試合に満たなければあるだけ。
     {"date":"2026-09-24", "opp":"相手の日本語名", "opp_rank":"相手の順位やランク（分かれば）", "comp":"大会・ラウンド",
      "ha":"H|A|N", "score":"自分側を先に 3-1", "res":"W|L|D",
      "units_won": 3, "units_lost": 1,          // unit が "なし" の競技は省略。テニス等はセット数、CS2はマップ数、スヌーカーはフレーム数、ダーツはレッグ数
      "detail":"6-4 3-6 6-2 / Mirage 13-9 など（任意）"}
   ],
   "lineup": ["先発・欠場・ロスター変更を1項目1行"]
 },
 "right": { 同じ形 },
 // 共通の対戦相手（60日以内の全試合）用：left.history / right.history に、試合日から60日以内で
 // 「もう一方のチームも60日以内に対戦した相手」との試合を全部1試合1行で入れる（形は form と同じ。form と重なる試合も入れてよい、自動で1つにまとめる）。
 // 例：left.history = [{"date":"2026-05-02","opp":"C","comp":"...","score":"2-1","res":"W","units_won":2,"units_lost":1}]
 "h2h": [ // 過去の直接対戦を最大10件、新しい順。winner は left|right|draw
   {"date":"2025-06-07","event":"大会・ラウンド","score":"左側を先に 2-1","winner":"left","units_left":2,"units_right":1,"detail":"任意"} ],
 "common_opponents_notes": ["直近10試合以外で分かる共通相手の結果があれば1行ずつ（任意）"],
 "venue": "会場・ホーム/アウェイ・中立（1行）",
 "esports": {"format":"BO3","lan_online":"...","map_pool":"...","veto":"...","patch":"...","map_h2h":"..."},  // eスポーツのみ
 "risks": ["..."], "missing": ["..."],
 "unavailable": {"h2h":"理由","left.form":"理由","right.form":"理由"},
 "source_urls": ["..."]
}
名前の書き方：相手チーム名・選手名は、共通相手の突き合わせができるように両チームで同じ表記にそろえる。

集計（直近の勝敗・勝率・ホーム/アウェイ別・連勝連敗・セット等の取得/喪失・得点-失点・H2H通算と得点合計・セット等合計・セット内の得点（ゲーム数・ラウンド数）合計・共通の対戦相手＝試合日から60日以内の全試合（form＋history）で比較・新しい対戦ほど上・勝率が同じなら得失差で比較）は手で書かない。`python -m rmc.build` が行データから `calc` を計算して書き込み、`python -m rmc.validate` が一致を検査する。


## ⑤ 格差候補発見エンジンの候補に追加で書く項目（rmc/discover.py）
```
"metrics": {"left": {"elo":…, "rank":…, "rating":…, "surface_elo":…, "season_wr":…, "wr_52w":…, "surface_wr":…, "pts_rate":…,
                     "gd_pg":…, "pd_pg":…, "rd_pg":…, "net_rating":…, "league_wr":…, "avg3":…, "checkout_pct":…,
                     "starter_confirmed": true, "starter_fip":…, "starter_era":…, "starter_kbb_pct":…},
            "right": {…}, "source": "出典"},          // 取れるものだけ。数字を作らない
"current_competition": {"left": {"played":…, "W":…, "D":…, "L":…, "gf":…, "ga":…}, "right": {…}, "source": "…"},
"deep5": {"ranking":"…", "current_competition":"…", "h2h_all":"…", "h2h_points":"…", "h2h_home_away":"…", "last5":"…", "last10":"…",
          "avg_points":"…", "streak":"…", "common_60d":"…", "first_rate":"先制率/第1セット/Map1", "absences":"…", "roster_changes":"…",
          "bo_format":"BO3", "lan_online":"LAN",
          "goalie":"…", "save_pct":"…", "gsaa":"…", "pp_pct":"…", "pk_pct":"…",   // アイスホッケー
          "first_set_rate":"…",                                                     // バレーボール
          "starters":"…"},                                                          // 野球
"counter_evidence": {"主力欠場": {"finding":"…", "impact":"none|minor|major", "applies": false}, … 全10項目 …},
"esports": {"map_winrates": {"left": {"Mirage": {"w":3,"l":1}}, "right": {…}}},
"boxing": {"rating":"…", "opp_level":"…", "weight_class":"…", "recent_fights":"…", "age":"…", "layoff":"…",
           "rating_gap": true, "rating_side": "L", "record_gap": true, "record_side": "L"}
```
取れない項目は unavailable に「項目名（deep5 のキーか日本語名）: 理由」。クリケットは form・h2h の comp／event に形式（ODI・T20I 等）を必ず書く。
