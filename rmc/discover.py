"""⑤ 格差候補発見エンジン（ユーザー指示 2026-09-29、GPTレビュー反映版）。
①推奨・②VALUE①・③VALUE②・④PRO EDGE とは完全に独立した前段工程。目的は「賭ける試合を選ぶ」ことではなく
「世界中から客観的な戦力差が極端な試合を取り逃さず発見する」こと。毎回の定時更新で必ず実行する。

絶対ルール
- 候補発見（screen）ではオッズを使わない。indicators()/screen()/finalize はオッズを受け取らない（引数にもない）。
- 市場オッズは⑤-A/⑤-B が確定したあと verify() で初めて付ける。オッズを見てから⑤の判定は変えない。
  市場との一致・不一致は別項目（market.agrees）として記録するだけ。
- 「競技ごとに必ず1試合出す」ルールは⑤では使わない。基準を満たす試合がなければ
  「本日はこの競技に明確な格差候補なし」。大会数・競技数・候補数に上限はない。
- 一次条件は「1項目でも異常なら深掘り対象」。該当数（例：一次条件12項目中5項目該当）は深掘りの優先順位にだけ使い、
  採用スコアにはしない。
- Rating/Elo差 ＞ ランキング順位差。Rating が取れない場合だけ順位差を使う。

処理順序
  全競技・全大会の日程 → 全試合の基本指標（オッズなし）→ 異常値スクリーニング → 候補だけ完全深掘り
  → 反対材料探索（支持材料と分離）→ 格差候補確定（⑤-A/⑤-B、型）→ 最後にオッズ取得（⑤-C 市場だけ格差）→ ①〜④へ渡す

使い方
  python -m rmc.discover screen   <locked_at>   … 一次候補（深掘り対象リスト）を data/discovery/latest.json に書く
  python -m rmc.discover finalize <locked_at>   … 深掘り・反対材料を読んで確定し、最後にオッズを付ける
"""
import glob, json, os, re, sys
from . import core
from .facts import _norm, _pts

ESPORTS = {"CS2", "VALORANT", "Dota 2", "LoL", "Rainbow Six", "King of Glory", "Mobile Legends", "CrossFire",
           "StarCraft: BW", "StarCraft II", "World of Tanks", "Standoff 2", "Call of Duty", "Overwatch 2",
           "Rocket League", "Honor of Kings", "Arena of Valor", "Warcraft", "Hearthstone", "Halo", "PUBG"}
SIM_FLAGS = {"シミュレーション/バーチャル（実力データなし）", "バトルロイヤル（1対1の勝敗市場なし）"}
ESPORTS_RATING_SOURCE = {"CS2": "HLTV/VRS", "VALORANT": "VLR等", "LoL": "チームRating＋リーグ成績",
                         "Dota 2": "Rating＋大会成績", "Rainbow Six": "Rating＋マップ成績",
                         "Mobile Legends": "リーグ・大会成績＋シリーズ/ゲーム成績", "King of Glory": "リーグ・大会成績＋シリーズ/ゲーム成績",
                         "Arena of Valor": "リーグ・大会成績＋シリーズ/ゲーム成績"}
TT_LOCAL = re.compile(r"setka|tt cup|tt elite|liga pro|win cup|tt star|pro league|czech", re.I)

# ---------------- 一次条件 ----------------
# 1行 = (条件キー, 表示名, しきい値, 指標キー, 前提)。前提：
#   "rating_first:<rating指標>" … その Rating 指標が取れているときは使わない（Rating 優先）
#   "min_n:<k>" … 指標の件数 n がこれ以上
#   "starter" … 両先発確定時のみ
C_COMMON = [
    ("last10_wr_diff", "直近10勝率差40pt以上", 40, "last10_wr_diff", None),
    ("h2h_wr", "H2H勝率75%以上（最低2試合）", 75, "h2h_wr", "min_n:2"),
    ("streak_w5", "5連勝以上", 5, "streak_w", None),
    ("streak_l5", "5連敗以上", 5, "streak_l", None),
    ("last10_8w", "片側が直近10で8勝以上", 8, "last10_top_w", None),
    ("last10_2w", "片側が直近10で2勝以下", 1, "last10_low_w", None),
]


def _r(key, label, th, ind=None, pre=None):
    return (key, label, th, ind or key, pre)


RULES = {
    "サッカー": C_COMMON + [
        _r("elo_diff", "Elo差200以上", 200, "elo_diff"),
        _r("fifa_rank_diff", "FIFAランキング差60以上（Eloが取れない場合）", 60, "fifa_rank_diff", "rating_first:elo_diff"),
        _r("cur_wr_diff", "現在大会勝率差40pt以上", 40),
        _r("cur_gd_diff", "現在大会得失点差の差15以上", 15),
        _r("h2h_avg_gd", "H2H平均得失点差+1.5以上", 1.5),
        _r("last10_gd_diff", "直近10得失点差の差15以上", 15),
    ],
    "_esports": C_COMMON + [
        _r("elo_diff", "Rating/Elo差150以上", 150, "elo_diff"),
        _r("rank_diff", "ランキング差50位以上（Ratingが取れない場合）", 50, "rank_diff", "rating_first:elo_diff"),
        _r("h2h_map_wr", "H2H maps勝率75%以上（最低4マップ）", 75),
        _r("h2h_map_diff", "H2H map差+4以上", 4),
        _r("same_map_wr_diff", "同一マップ勝率差25pt以上", 25),
    ],
    "テニス": C_COMMON + [
        _r("elo_diff", "総合Elo差150以上", 150),
        _r("surface_elo_diff", "サーフェスElo差125以上", 125),
        _r("tennis_rank", "ATP/WTAランク：上位側100位以内で差80位以上、または順位比4倍以上（Eloが取れない場合）", 1, "tennis_rank", "rating_first:elo_diff"),
        _r("wr52_diff", "直近52週勝率差25pt以上", 25),
        _r("surface_wr_diff", "同サーフェス勝率差25pt以上", 25),
        _r("last10_unit_diff", "直近10セット率差25pt以上", 25),
        _r("h2h_unit_rate", "H2Hセット率80%以上（2試合以上）", 80, "h2h_unit_rate", "min_n:2"),
        _r("h2h_3_0", "H2H 3勝0敗以上", 3, "h2h_sweep"),
        _r("common_diff", "共通相手：セット得失差の差+1.5以上／試合", 1.5),
    ],
    "アイスホッケー": C_COMMON + [
        _r("elo_diff", "Elo/Rating差150以上", 150),
        _r("pts_rate_diff", "リーグ内の勝点率差.300以上（最低8試合）", 0.300),
        _r("gd_pg_diff", "1試合平均の得失点差の差1.5以上", 1.5),
        _r("h2h_avg_gd", "H2H平均得失点差+2.0以上（2試合以上）", 2.0),
        _r("common_diff", "共通相手：得失点差の差+1.5以上／試合", 1.5),
    ],
    "バスケットボール": C_COMMON + [
        _r("net_rating_diff", "Net Rating差10以上", 10),
        _r("pd_pg_diff", "平均得失点差の差12以上（Net Ratingが取れない場合）", 12, "pd_pg_diff", "rating_first:net_rating_diff"),
        _r("season_wr_diff", "勝率差35pt以上（最低6試合）", 35),
        _r("h2h_avg_gd", "H2H平均点差12以上（2試合以上）", 12),
        _r("elo_diff", "Elo差150以上", 150),
        _r("common_diff", "共通相手：得失点差の差+12以上／試合", 12),
    ],
    "野球": C_COMMON + [
        _r("fip_diff", "先発FIP差1.25以上（両先発確定時のみ）", 1.25, "fip_diff", "starter"),
        _r("era_diff", "先発ERA差1.75以上（両先発確定時のみ）", 1.75, "era_diff", "starter"),
        _r("kbb_diff", "先発K-BB%差8pt以上（両先発確定時のみ）", 8, "kbb_diff", "starter"),
        _r("rd_starter_same", "チーム得失点差＋先発差が同方向（両先発確定時のみ）", 1, "rd_starter_same", "starter"),
        _r("season_wr_diff", "今季勝率差.150以上（15pt）", 15),
        _r("rd_pg_diff", "1試合平均の得失点差の差1.5以上", 1.5),
        _r("common_diff", "共通相手：得失点差の差+1.5以上／試合", 1.5),
    ],
    "ダーツ": C_COMMON + [
        _r("rank_diff", "PDCオーダーオブメリット差40位以上（上位側32位以内）", 40, "oom_rank"),
        _r("avg3_diff", "3ダーツ平均の差4.0以上", 4.0),
        _r("checkout_diff", "チェックアウト率差6pt以上", 6),
    ],
    "スヌーカー": C_COMMON + [
        _r("rank_diff", "世界ランク差40位以上（上位側16位以内）", 40, "snooker_rank"),
        _r("season_wr_diff", "今季勝率差25pt以上（最低8試合）", 25),
        _r("h2h_unit_rate", "H2Hフレーム率70%以上（2試合以上）", 70, "h2h_unit_rate", "min_n:2"),
        _r("last10_unit_diff", "直近10のフレーム率差25pt以上", 25),
    ],
    "卓球（国際/WTT）": C_COMMON + [
        _r("elo_diff", "Rating差150以上", 150),
        _r("rank_diff", "ITTF/WTTランキング差100位以上（Ratingが取れない場合）", 100, "rank_diff", "rating_first:elo_diff"),
        _r("last10_unit_diff", "直近10のゲーム率差25pt以上", 25),
    ],
    "卓球（Setka Cup等の独立・下位大会）": C_COMMON + [
        _r("league_wr_diff", "同一リーグ今月の勝率差40pt以上（最低10試合）", 40),
        _r("last10_unit_diff", "直近10のゲーム率差25pt以上", 25),
    ],
    "クリケット": C_COMMON + [   # 形式（Test/ODI/T20/T20I）を絶対に混ぜない：form・h2h は同一形式の行だけ
        _r("rating_diff", "ICCチームランキングのレーティング差20以上（同一形式）", 20),
    ],
    "バレーボール": C_COMMON + [
        _r("rating_diff", "FIVB Rating差50以上", 50),
        _r("rank_diff", "世界順位差30以上（Ratingが取れない場合）", 30, "rank_diff", "rating_first:rating_diff"),
        _r("h2h_unit_rate", "H2Hセット率75%以上（最低2試合）", 75, "h2h_unit_rate", "min_n:2"),
        _r("last10_unit_diff", "直近10セット率差25pt以上", 25),
        _r("last10_unit_avg_diff", "直近10平均セット差の差1.0以上", 1.0),
        _r("pts_rate_diff", "リーグ順位の勝点率差.300以上", 0.300),
    ],
    "ハンドボール": C_COMMON + [
        _r("pts_rate_diff", "リーグ内の勝点率差.350以上", 0.350),
        _r("gd_pg_diff", "1試合平均の得失点差の差6以上", 6),
        _r("h2h_avg_gd", "H2H平均得失点差+5以上（2試合以上）", 5),
    ],
    "水球": C_COMMON + [
        _r("gd_pg_diff", "1試合平均の得失点差の差5以上", 5),
    ],
    "バドミントン": C_COMMON + [
        _r("rank_diff", "BWFランキング差30位以上（上位側20位以内）", 30, "bwf_rank"),
        _r("last10_unit_diff", "直近10のゲーム率差30pt以上", 30),
    ],
    "ラグビー": C_COMMON + [
        _r("rating_diff", "World Rugbyランキングポイント差10以上（代表）", 10),
        _r("pts_rate_diff", "リーグ内の勝点率差.350以上", 0.350),
        _r("gd_pg_diff", "1試合平均の得失点差の差15以上", 15),
    ],
    "アメフト": C_COMMON + [
        _r("elo_diff", "Elo差150以上", 150),
        _r("gd_pg_diff", "1試合平均の得失点差の差12以上", 12),
    ],
    "ボクシング": [   # 戦績だけでは相手の質が分からないので自動抽出は慎重に（確定には BOXING_REQUIRED が必要）
        _r("rating_diff", "BoxRec等のRating差（上位側が明確に上）", 1, "boxrec_gap"),
        _r("record_gap", "上位側が無敗または勝率90%以上で、相手の直近5戦が2勝以下", 1, "boxing_record"),
    ],
}
RULES["ラグビーリーグ"] = RULES["ラグビー"]
BOXING_REQUIRED = ("rating", "opp_level", "weight_class", "recent_fights", "age", "layoff")
BOXING_LABEL = {"rating": "BoxRec等のRating", "opp_level": "対戦相手レベル", "weight_class": "階級", "recent_fights": "直近試合",
                "age": "年齢", "layoff": "長期ブランク"}

GROUPS = {"elo_diff": "rating", "surface_elo_diff": "rating", "rank_diff": "rating", "fifa_rank_diff": "rating", "tennis_rank": "rating",
          "rating_diff": "rating", "net_rating_diff": "rating", "oom_rank": "rating",
          "cur_wr_diff": "current", "cur_gd_diff": "current", "pts_rate_diff": "current", "season_wr_diff": "current",
          "league_wr_diff": "current", "wr52_diff": "current", "surface_wr_diff": "current", "gd_pg_diff": "current",
          "pd_pg_diff": "current", "rd_pg_diff": "current", "avg3_diff": "current", "checkout_diff": "current",
          "h2h_wr": "h2h", "h2h_avg_gd": "h2h", "h2h_map_wr": "h2h", "h2h_map_diff": "h2h", "h2h_unit_rate": "h2h", "h2h_3_0": "h2h",
          "last10_wr_diff": "form", "last10_gd_diff": "form", "streak_w5": "form", "streak_l5": "form", "last10_8w": "form",
          "last10_2w": "form", "last10_unit_diff": "form", "last10_unit_avg_diff": "form", "same_map_wr_diff": "form",
          "common_diff": "common", "fip_diff": "pitcher", "era_diff": "pitcher", "kbb_diff": "pitcher", "rd_starter_same": "pitcher",
          "record_gap": "form"}
GROUP_LABEL = {"rating": "Rating/ランキング", "current": "現在大会・今季成績", "h2h": "H2H", "form": "直近成績",
               "common": "共通相手比較", "pitcher": "先発投手"}

# 候補の完全深掘りで必ず埋める項目（facts.deep5。取れなければ facts.unavailable に「項目名: 理由」）
DEEP_KEYS = ("ranking", "current_competition", "h2h_all", "h2h_points", "h2h_home_away", "last5", "last10", "avg_points",
             "streak", "common_60d", "first_rate", "absences", "roster_changes", "bo_format", "lan_online")
DEEP_LABEL = {"ranking": "ランキング", "current_competition": "現在大会成績", "h2h_all": "H2H確認可能全件",
              "h2h_points": "H2H得失点", "h2h_home_away": "ホーム/アウェーH2H", "last5": "直近5", "last10": "直近10",
              "avg_points": "平均得失点", "streak": "連勝/連敗", "common_60d": "過去60日の共通対戦相手",
              "first_rate": "先制率/第1セット/Map1", "absences": "欠場", "roster_changes": "ロスター変更",
              "bo_format": "BO", "lan_online": "LAN/Online",
              "goalie": "先発GK", "save_pct": "Save%", "gsaa": "GSAA等", "pp_pct": "PP%", "pk_pct": "PK%",
              "first_set_rate": "第1セット勝率", "starters": "先発投手"}
DEEP_EXTRA = {"アイスホッケー": ("goalie", "save_pct", "gsaa", "pp_pct", "pk_pct"),
              "バレーボール": ("first_set_rate",), "野球": ("starters",)}
ESPORTS_ONLY = ("bo_format", "lan_online")
COUNTER_KEYS = ("主力欠場", "ローテーション", "世代交代", "古いH2H", "ホーム/アウェー差", "最近の急改善", "BO1",
                "LAN/Online差", "ロスター変更", "消化試合")
IMPACTS = ("none", "minor", "major")        # major＝格差の根拠を崩す（→ 反対材料で保留）
UNCERTAIN_KEYS = {"主力欠場", "ロスター変更", "ホーム/アウェー差", "古いH2H", "最近の急改善", "BO1", "LAN/Online差"}
MARKET_C_NV = 0.80                          # ⑤-C：市場の控除後本命勝率がこれ以上なのに独立データで確認できていない
GRADE_LABEL = {"A": "⑤-A 強い格差確認", "B": "⑤-B 格差候補・要注意", "C": "⑤-C 市場だけ格差"}
TYPE_LABEL = {"multi": "複合格差型", "h2h": "H2H再現型", "current": "現在大会型", "power": "現在戦力型"}


def group_of(match):
    sp = match.get("sport")
    if sp in ESPORTS:
        return sp
    if sp == "卓球":
        return "卓球（Setka Cup等の独立・下位大会）" if TT_LOCAL.search(str(match.get("competition") or "")) else "卓球（国際/WTT）"
    return sp


def rules_for(match):
    g = group_of(match)
    if g in ESPORTS:
        return RULES["_esports"]
    return RULES.get(g)


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _ua(reason):
    return {"unavailable": reason}


def _side(d):
    return "L" if d > 0 else "R" if d < 0 else None


def cricket_format(text):
    t = str(text or "").lower()
    if "t20i" in t or ("t20" in t and "international" in t):
        return "T20I"
    if "t20" in t:
        return "T20"
    if "odi" in t or "one day" in t or "one-day" in t:
        return "ODI"
    if "test" in t:
        return "Test"
    return None


def _rows(side, fmt=None):
    rows = [g for g in (side.get("form") or []) if g.get("res") in ("W", "L", "D")]
    if fmt:
        rows = [g for g in rows if cricket_format(g.get("comp")) == fmt]
    return rows


def _wr(rows):
    return sum(1 for g in rows if g["res"] == "W") / len(rows) * 100 if rows else None


def _gd(rows):
    ps = [_pts(g.get("score"), g.get("res")) for g in rows]
    ps = [p for p in ps if p]
    return (sum(a - b for a, b in ps), len(ps)) if ps else (None, 0)


def _units(rows):
    u = [(g["units_won"], g["units_lost"]) for g in rows if _num(g.get("units_won")) is not None and _num(g.get("units_lost")) is not None]
    return u


def _streak(rows):
    if not rows:
        return None, 0
    r0, n = rows[0]["res"], 0
    for g in rows:
        if g["res"] != r0:
            break
        n += 1
    return r0, n


# ---------------- レーティング（自動取得・オッズではない客観指標）----------------
def load_ratings():
    out = {}
    for f in glob.glob(core.path("ratings", "*.json")):
        try:
            x = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not x.get("ok", True):
            continue
        tb = {_norm(n): dict(v, name=n) for n, v in (x.get("teams") or {}).items()}
        if tb:
            out[x.get("system") or os.path.basename(f)[:-5]] = dict(taken_at=x.get("taken_at"), sports=x.get("sports") or [], teams=tb)
    return out


def _lookup(ratings, sport, name):
    k = _norm(name)
    for sysname, r in ratings.items():
        if sport in r["sports"] and k in r["teams"]:
            return sysname, r["teams"][k], r["taken_at"]
    return None, None, None


def _metric(fx, match, ratings, fld):
    """facts.metrics（深掘りで記録）→ data/ratings（自動取得）の順で左右の値を取る。"""
    mt = fx.get("metrics") or {}
    a, b = _num((mt.get("left") or {}).get(fld)), _num((mt.get("right") or {}).get(fld))
    if a is not None and b is not None:
        return a, b, mt.get("source") or "facts.metrics"
    sa, ra, ta = _lookup(ratings, match.get("sport"), match.get("left"))
    sb, rb, tb = _lookup(ratings, match.get("sport"), match.get("right"))
    if ra and rb and sa == sb and _num(ra.get(fld)) is not None and _num(rb.get(fld)) is not None:
        return ra[fld], rb[fld], f"{sa}（{ta}取得）"
    return None, None, None


# ---------------- 基本指標（オッズを使わない）----------------
def indicators(match, facts, ratings):
    """1試合の基本指標。value＝差の大きさ、side＝有利側（L/R）。取れないものは unavailable＋理由。
    オッズ・価格は一切参照しない（引数にもない）。"""
    fx = facts or {}
    L, R = fx.get("left") or {}, fx.get("right") or {}
    sport = match.get("sport")
    fmt = cricket_format(match.get("competition")) if sport == "クリケット" else None
    ind = {}
    if sport == "クリケット" and not fmt:
        ind["_format"] = _ua("試合の形式（Test/ODI/T20/T20I）が判定できない：形式を混ぜないため直近・H2Hは使わない")

    def diff(key, fld, higher_better=True, scale=1):
        a, b, src = _metric(fx, match, ratings, fld)
        if a is None:
            ind[key] = _ua(f"{fld} が両者そろって取れない")
            return
        d = (a - b) if higher_better else (b - a)
        ind[key] = dict(value=round(abs(d) * scale, 3), side=_side(d), left=a, right=b, source=src)

    diff("elo_diff", "elo")
    diff("surface_elo_diff", "surface_elo")
    diff("rank_diff", "rank", higher_better=False)
    diff("fifa_rank_diff", "fifa_rank", higher_better=False)
    diff("rating_diff", "rating")
    diff("net_rating_diff", "net_rating")
    diff("pd_pg_diff", "pd_pg")
    diff("rd_pg_diff", "rd_pg")
    diff("gd_pg_diff", "gd_pg")
    diff("pts_rate_diff", "pts_rate")
    diff("season_wr_diff", "season_wr")
    diff("wr52_diff", "wr_52w")
    diff("surface_wr_diff", "surface_wr")
    diff("league_wr_diff", "league_wr")
    diff("avg3_diff", "avg3")
    diff("checkout_diff", "checkout_pct")
    # ランク系の特殊条件（上位側の順位制限つき）
    for key, top, gap in (("tennis_rank", 100, 80), ("oom_rank", 32, 40), ("snooker_rank", 16, 40), ("bwf_rank", 20, 30)):
        v = ind.get("rank_diff")
        if not v or "unavailable" in v:
            ind[key] = _ua("ランキングが両者そろって取れない"); continue
        hi, lo = min(v["left"], v["right"]), max(v["left"], v["right"])
        hit = hi <= top and (lo - hi) >= gap or (key == "tennis_rank" and hi > 0 and lo / hi >= 4 and hi <= 300)
        ind[key] = dict(value=1 if hit else 0, side=v["side"], left=v["left"], right=v["right"], source=v.get("source"),
                        note=f"上位側{hi}位・差{lo - hi}位・比{lo / hi:.1f}倍" if hi else None)
    # 野球：先発（両先発確定時のみ）
    mt = fx.get("metrics") or {}
    starters_ok = bool((mt.get("left") or {}).get("starter_confirmed")) and bool((mt.get("right") or {}).get("starter_confirmed"))
    if sport == "野球":
        if starters_ok:
            diff("fip_diff", "starter_fip", higher_better=False)
            diff("era_diff", "starter_era", higher_better=False)
            diff("kbb_diff", "starter_kbb_pct")
            f, r = ind.get("fip_diff") or {}, ind.get("rd_pg_diff") or {}
            if "unavailable" not in f and "unavailable" not in r and f.get("side") and f.get("side") == r.get("side"):
                ind["rd_starter_same"] = dict(value=1, side=f["side"], note="チーム得失点差と先発FIP差が同方向")
            else:
                ind["rd_starter_same"] = _ua("先発FIPかチーム得失点差が取れない、または方向が違う")
        else:
            for k in ("fip_diff", "era_diff", "kbb_diff", "rd_starter_same"):
                ind[k] = _ua("先発未確定")
    # 現在大会（facts.current_competition：{"left":{"played","W","D","L","gf","ga"},"right":{...}}）
    cc = fx.get("current_competition") or {}
    cl, cr = cc.get("left") or {}, cc.get("right") or {}
    if _num(cl.get("played")) and _num(cr.get("played")):
        wl, wr = cl.get("W", 0) / cl["played"] * 100, cr.get("W", 0) / cr["played"] * 100
        ind["cur_wr_diff"] = dict(value=round(abs(wl - wr), 1), side=_side(wl - wr), left=round(wl, 1), right=round(wr, 1),
                                  n=(cl["played"], cr["played"]), source=cc.get("source"))
        if all(_num(x.get(k)) is not None for x in (cl, cr) for k in ("gf", "ga")):
            d = (cl["gf"] - cl["ga"]) - (cr["gf"] - cr["ga"])
            ind["cur_gd_diff"] = dict(value=abs(d), side=_side(d), left=cl["gf"] - cl["ga"], right=cr["gf"] - cr["ga"])
        else:
            ind["cur_gd_diff"] = _ua("現在大会の得失点がない")
    else:
        ind["cur_wr_diff"] = ind["cur_gd_diff"] = _ua("現在大会の成績（facts.current_competition）がない")
    # 直近10（クリケットは同一形式のみ）
    use_fmt = fmt if sport == "クリケット" else None
    if sport == "クリケット" and not fmt:
        lr = rr = []
    else:
        lr, rr = _rows(L, use_fmt)[:10], _rows(R, use_fmt)[:10]
    if len(lr) >= 5 and len(rr) >= 5:
        d = _wr(lr) - _wr(rr)
        ind["last10_wr_diff"] = dict(value=round(abs(d), 1), side=_side(d), left=round(_wr(lr), 1), right=round(_wr(rr), 1), n=(len(lr), len(rr)))
        (gl, nl), (gr, nr) = _gd(lr), _gd(rr)
        ind["last10_gd_diff"] = (dict(value=abs(gl - gr), side=_side(gl - gr), left=gl, right=gr, n=(nl, nr))
                                 if nl >= 5 and nr >= 5 else _ua("直近のスコアが5試合未満"))
        ul, ur = _units(lr), _units(rr)
        if len(ul) >= 5 and len(ur) >= 5:
            ra = sum(a for a, _ in ul) / max(1, sum(a + b for a, b in ul)) * 100
            rb = sum(a for a, _ in ur) / max(1, sum(a + b for a, b in ur)) * 100
            ind["last10_unit_diff"] = dict(value=round(abs(ra - rb), 1), side=_side(ra - rb), left=round(ra, 1), right=round(rb, 1))
            aa = sum(a - b for a, b in ul) / len(ul); ab = sum(a - b for a, b in ur) / len(ur)
            ind["last10_unit_avg_diff"] = dict(value=round(abs(aa - ab), 2), side=_side(aa - ab), left=round(aa, 2), right=round(ab, 2))
        else:
            ind["last10_unit_diff"] = ind["last10_unit_avg_diff"] = _ua("直近のセット/マップ/ゲーム数が5試合未満")
    else:
        for k in ("last10_wr_diff", "last10_gd_diff", "last10_unit_diff", "last10_unit_avg_diff"):
            ind[k] = _ua(f"直近成績が5試合未満（左{len(lr)}・右{len(rr)}）" + ("・同一形式のみ" if use_fmt else ""))
    # 連勝・連敗・直近10の勝数（片側だけで条件になる）
    al, ar = (_rows(L, use_fmt), _rows(R, use_fmt)) if not (sport == "クリケット" and not fmt) else ([], [])
    if al and ar:
        sl, sr = _streak(al), _streak(ar)
        w = [(n, s) for (r, n), s in ((sl, "L"), (sr, "R")) if r == "W"]
        l = [(n, s) for (r, n), s in ((sl, "L"), (sr, "R")) if r == "L"]
        bw = max(w) if w else (0, None)
        bl = max(l) if l else (0, None)
        ind["streak_w"] = dict(value=bw[0], side=bw[1], left=f"{sl[1]}連{sl[0]}", right=f"{sr[1]}連{sr[0]}")
        ind["streak_l"] = dict(value=bl[0], side=("R" if bl[1] == "L" else "L") if bl[1] else None, left=f"{sl[1]}連{sl[0]}", right=f"{sr[1]}連{sr[0]}")
        wl10 = sum(1 for g in al[:10] if g["res"] == "W"); wr10 = sum(1 for g in ar[:10] if g["res"] == "W")
        top = max((wl10, "L"), (wr10, "R"))
        ind["last10_top_w"] = dict(value=top[0], side=top[1], left=f"{wl10}勝/{len(al[:10])}", right=f"{wr10}勝/{len(ar[:10])}")
        low = [(x, s) for x, s, n in ((wl10, "L", len(al[:10])), (wr10, "R", len(ar[:10]))) if n >= 8 and x <= 2]
        ind["last10_low_w"] = (dict(value=1, side="R" if min(low)[1] == "L" else "L", left=f"{wl10}勝/{len(al[:10])}", right=f"{wr10}勝/{len(ar[:10])}")
                               if low else dict(value=0, side=None, left=f"{wl10}勝/{len(al[:10])}", right=f"{wr10}勝/{len(ar[:10])}"))
    else:
        for k in ("streak_w", "streak_l", "last10_top_w", "last10_low_w"):
            ind[k] = _ua("直近成績がない")
    # H2H（クリケットは同一形式のみ）
    h = [g for g in (fx.get("h2h") or []) if g.get("winner") in ("left", "right", "draw")]
    if use_fmt:
        h = [g for g in h if cricket_format(g.get("event")) == use_fmt]
    elif sport == "クリケット":
        h = []
    if len(h) >= 2:
        wl = sum(1 for g in h if g["winner"] == "left"); wr_ = sum(1 for g in h if g["winner"] == "right")
        ind["h2h_wr"] = dict(value=round(max(wl, wr_) / len(h) * 100, 1), side="L" if wl > wr_ else "R" if wr_ > wl else None, n=len(h), rec=f"{wl}-{wr_}")
        ind["h2h_sweep"] = dict(value=max(wl, wr_) if min(wl, wr_) == 0 else 0, side="L" if wl > wr_ else "R", rec=f"{wl}-{wr_}")
        ps = [p for p in (_pts(g.get("score"), g["winner"]) for g in h) if p]
        ind["h2h_avg_gd"] = (dict(value=round(abs(sum(a - b for a, b in ps) / len(ps)), 2), side=_side(sum(a - b for a, b in ps)), n=len(ps))
                             if len(ps) >= 2 else _ua("H2Hのスコアが2試合未満"))
        us = [(g["units_left"], g["units_right"]) for g in h if _num(g.get("units_left")) is not None and _num(g.get("units_right")) is not None]
        ml, mr = sum(a for a, _ in us), sum(b for _, b in us)
        if ml + mr >= 4:
            ind["h2h_map_wr"] = dict(value=round(max(ml, mr) / (ml + mr) * 100, 1), side="L" if ml > mr else "R" if mr > ml else None, units=f"{ml}-{mr}")
            ind["h2h_map_diff"] = dict(value=abs(ml - mr), side=_side(ml - mr), units=f"{ml}-{mr}")
        else:
            ind["h2h_map_wr"] = ind["h2h_map_diff"] = _ua("H2Hのマップ（セット等）数が4未満")
        ind["h2h_unit_rate"] = (dict(value=round(max(ml, mr) / (ml + mr) * 100, 1), side="L" if ml > mr else "R" if mr > ml else None, n=len(us), units=f"{ml}-{mr}")
                                if len(us) >= 2 and ml + mr else _ua("H2Hのセット等の記録が2試合未満"))
    else:
        for k in ("h2h_wr", "h2h_sweep", "h2h_avg_gd", "h2h_map_wr", "h2h_map_diff", "h2h_unit_rate"):
            ind[k] = _ua(f"H2Hが{len(h)}試合（2試合未満）" + ("・同一形式のみ" if use_fmt else ""))
    # 同一マップ勝率（facts.esports.map_winrates）
    mw = ((fx.get("esports") or {}).get("map_winrates")) or {}
    best = None
    for mp, a in (mw.get("left") or {}).items():
        b = (mw.get("right") or {}).get(mp)
        if isinstance(a, dict) and isinstance(b, dict):
            na, nb = a.get("w", 0) + a.get("l", 0), b.get("w", 0) + b.get("l", 0)
            if na >= 3 and nb >= 3:
                d = a["w"] / na * 100 - b["w"] / nb * 100
                if best is None or abs(d) > best["value"]:
                    best = dict(value=round(abs(d), 1), side=_side(d), map=mp, n=(na, nb))
    ind["same_map_wr_diff"] = best or _ua("両者3マップ以上の同一マップ勝率がない")
    ind["common_diff"] = common_differential(fx, units=sport in ("テニス",))
    # ボクシング（戦績だけでは確定しない）
    if sport == "ボクシング":
        bx = fx.get("boxing") or {}
        gap = bx.get("rating_gap")
        ind["boxrec_gap"] = dict(value=1, side=bx.get("rating_side")) if gap and bx.get("rating_side") else _ua("BoxRec等のRatingが取れない")
        ind["boxing_record"] = dict(value=1, side=bx.get("record_side")) if bx.get("record_gap") and bx.get("record_side") else _ua("戦績条件を確認できない")
    return ind


def common_differential(fx, units=False):
    """Common Opponent Differential：60日以内の共通相手（2件以上）について、同じ相手への平均得失差の差。"""
    rows = ((fx.get("calc") or {}).get("common")) or []
    diffs = []
    for r in rows:
        def avg(lst):
            ps = [_pts(x.get("score"), x.get("res")) for x in lst]
            ps = [p for p in ps if p]
            return sum(a - b for a, b in ps) / len(ps) if ps else None
        a, b = avg(r.get("left") or []), avg(r.get("right") or [])
        if a is not None and b is not None:
            diffs.append(dict(opp=r.get("opp"), left=round(a, 2), right=round(b, 2), diff=round(a - b, 2)))
    if len(diffs) < 2:
        return _ua(f"60日以内の共通対戦相手（スコアあり）が{len(diffs)}件（2件未満は比較しない）")
    d = sum(x["diff"] for x in diffs) / len(diffs)
    return dict(value=round(abs(d), 2), side=_side(d), n=len(diffs), rows=diffs)


def screen(match, ind):
    """一次スクリーニング。(該当条件リスト, 条件総数) を返す。1条件でも候補（ここでは却下しない）。オッズは使わない。"""
    rules = rules_for(match)
    if not rules:
        return None, 0
    hits = []
    for key, label, th, ik, pre in rules:
        v = ind.get(ik) or {}
        if "unavailable" in v or v.get("side") is None:
            continue
        if pre and pre.startswith("rating_first:") and "unavailable" not in (ind.get(pre.split(":")[1]) or {"unavailable": 1}):
            continue      # Rating が取れているので順位差は使わない
        if pre and pre.startswith("min_n:") and (v.get("n") or 0) < int(pre.split(":")[1]):
            continue
        if v["value"] >= th:
            hits.append(dict(key=key, ind=ik, label=label, value=v["value"], side=v["side"], group=GROUPS.get(key, "form")))
    return hits, len(rules)


# ---------------- 深掘り・支持材料／反対材料・確定 ----------------
def deep_status(fx, match):
    fx = fx or {}
    sport = match.get("sport")
    un = [str(k) + " " + str(v) for k, v in (fx.get("unavailable") or {}).items()]
    dd = fx.get("deep5") or {}
    keys = [k for k in DEEP_KEYS if not (k in ESPORTS_ONLY and sport not in ESPORTS)] + list(DEEP_EXTRA.get(sport, ()))
    miss = []
    for k in keys:
        if dd.get(k) not in (None, "", [], {}):
            continue
        if any(k in u or DEEP_LABEL[k] in u for u in un):
            continue
        miss.append(DEEP_LABEL[k])
    if sport == "ボクシング":
        bx = (fx.get("boxing") or {})
        for k in BOXING_REQUIRED:
            if bx.get(k) in (None, "", [], {}):
                miss.append(BOXING_LABEL[k])
    return miss


def counter_status(fx):
    ce = (fx or {}).get("counter_evidence") or {}
    miss, major, minor = [], [], []
    for k in COUNTER_KEYS:
        v = ce.get(k)
        if not isinstance(v, dict) or v.get("impact") not in IMPACTS or not v.get("finding"):
            miss.append(k); continue
        if v["impact"] == "major":
            major.append(f"{k}：{v['finding']}")
        elif v["impact"] == "minor" or (k == "BO1" and v.get("applies")):
            minor.append((k, v["finding"]))
    return miss, major, minor


def support_list(ind, hits, side):
    out = []
    for h in hits:
        if h["side"] != side:
            continue
        v = ind.get(h.get("ind") or h["key"]) or {}
        extra = v.get("rec") or v.get("units") or v.get("note") or (f"{v.get('left')} 対 {v.get('right')}" if v.get("left") is not None else "")
        out.append(f"{h['label']}（{extra}）" if extra else h["label"])
    cd = ind.get("common_diff") or {}
    if "unavailable" not in cd and cd.get("side") == side and not any(h["key"] == "common_diff" for h in hits):
        out.append(f"共通相手比較 {'+' if side == 'L' else '-'}{cd['value']}（{cd['n']}件）")
    return out


def decide(match, ind, hits, fx):
    """深掘り・反対材料を踏まえて ⑤-A／⑤-B／保留 を決める（オッズは使わない）。"""
    votes = {"L": 0, "R": 0}
    for h in hits:
        votes[h["side"]] += 1
    side = "L" if votes["L"] > votes["R"] else "R" if votes["R"] > votes["L"] else None
    if side is None:
        return dict(status="反対材料で保留", reason="条件ごとに有利側が割れている（格差の方向が確定しない）")
    same = [h for h in hits if h["side"] == side]
    groups = {h["group"] for h in same}
    cd = ind.get("common_diff") or {}
    if "unavailable" not in cd and cd.get("side") == side:
        groups.add("common")
    h2h_n = (ind.get("h2h_wr") or {}).get("n", 0)
    typ = ("multi" if len(groups) >= 3 else "h2h" if "h2h" in groups else "current" if "current" in groups else "power")
    miss, major, minor = counter_status(fx)
    support = support_list(ind, hits, side)
    opposite = [h["label"] for h in hits if h["side"] != side]
    counter = [f"{k}：{f}" for k, f in minor] + [f"（重大）{x}" for x in major] + [f"逆側を指す一次条件：{x}" for x in opposite]
    base = dict(side=side, pick=match.get("left") if side == "L" else match.get("right"), type=typ, type_label=TYPE_LABEL[typ],
                groups=sorted(GROUP_LABEL[g] for g in groups), support=support, counter=counter)
    if major:
        return dict(base, status="反対材料で保留", reason="格差を崩す反対材料：" + "／".join(major))
    uncertain = []
    if h2h_n < 2:
        uncertain.append("H2H不足")
    uncertain += [k for k, _ in minor if k in UNCERTAIN_KEYS]
    if opposite:
        uncertain.append("逆側を指す条件あり")
    if group_of(match) == "卓球（Setka Cup等の独立・下位大会）" or "下位リーグ（整合性リスク）" in (match.get("flags") or []):
        uncertain.append("データ信頼度：低（独立・下位大会）")
    if match.get("sport") == "ボクシング":
        uncertain.append("ボクシング（戦績だけでは相手の質が分からない）")
    if len(groups) >= 2 and not uncertain:
        return dict(base, status="格差候補確定", grade="A", grade_label=GRADE_LABEL["A"])
    return dict(base, status="格差候補確定", grade="B", grade_label=GRADE_LABEL["B"],
                uncertainty=uncertain or ["独立した指標が1系統だけ"])


def _facts(mid):
    f = core.path("facts", f"{mid}.json")
    return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else None


def inventory(matches, locked):
    """判定時刻より後・24時間以内に始まる全試合（全競技・全大会）。"""
    return sorted(mid for mid, m in matches.items()
                  if m.get("start_jst") and m["start_jst"] > locked and core.within_horizon(locked, m["start_jst"]))


CAND = ("一次候補", "深掘り未完", "反対材料で保留", "格差候補確定")


def run_screen(locked, matches=None):
    matches = matches or core.load("matches.json", {})
    ratings = load_ratings()
    out = dict(engine="⑤ 格差候補発見エンジン", stage="screened", locked_at=locked, screened_at=core.now_jst(),
               odds_used_in_screening=False, ratings_sources={k: v["taken_at"] for k, v in ratings.items()},
               rows=[], by_sport={})
    for mid in inventory(matches, locked):
        m = matches[mid]
        row = dict(match_id=mid, sport=m.get("sport"), group=group_of(m), competition=m.get("competition"),
                   start_jst=m["start_jst"], left=m.get("left"), right=m.get("right"))
        if set(m.get("flags", [])) & SIM_FLAGS:
            row.update(status="対象外", reason="シミュレーション/バトルロイヤル（実力の指標がない）")
        else:
            fx = _facts(mid)
            ind = indicators(m, fx, ratings)
            row["indicators"] = ind
            row["indicators_available"] = sorted(k for k, v in ind.items() if "unavailable" not in v)
            hits, n = screen(m, ind)
            if hits is None:
                row.update(status="条件未定義", reason="この競技の一次条件が未定義")
            elif hits:
                row.update(status="一次候補", hits=hits, hit_count=len(hits), rule_count=n,
                           hit_summary=f"一次条件{n}項目中{len(hits)}項目該当", log=[f"発火：{h['label']}（値{h['value']}・{'左' if h['side'] == 'L' else '右'}側）" for h in hits])
            else:
                row.update(status="該当なし", rule_count=n,
                           reason=(f"取得できた指標{len(row['indicators_available'])}件でいずれも基準未満" if row["indicators_available"]
                                   else "取得できた指標なし（facts・自動レーティングとも無し）"))
            if m.get("sport") in ESPORTS:
                row["rating_source"] = ESPORTS_RATING_SOURCE.get(m.get("sport"), "利用可能なRating＋大会成績")
        out["rows"].append(row)
    out["rows"].sort(key=lambda r: (r.get("status") != "一次候補", -(r.get("hit_count") or 0), r["start_jst"]))
    _summ(out)
    return out


def run_finalize(locked, screened=None, matches=None, odds=None):
    matches = matches or core.load("matches.json", {})
    scr = screened or core.load("discovery/latest.json")
    ratings = load_ratings()
    for row in scr["rows"]:
        if row.get("status") not in CAND:
            continue
        m = matches[row["match_id"]]
        fx = _facts(row["match_id"])
        ind = indicators(m, fx, ratings)          # 深掘りで増えた指標で再計算（まだオッズなし）
        hits, n = screen(m, ind)
        hits = hits or row.get("hits") or []
        row.update(indicators=ind, hits=hits, hit_count=len(hits), rule_count=n or row.get("rule_count"),
                   hit_summary=f"一次条件{n or row.get('rule_count')}項目中{len(hits)}項目該当")
        miss = deep_status(fx, m) if fx else ["facts なし"]
        cmiss = counter_status(fx)[0]
        if miss or cmiss:
            row.update(status="深掘り未完", reason="未取得：" + "・".join(miss + [f"反対材料[{k}]" for k in cmiss]))
            continue
        row.update(decide(m, ind, hits, fx))
    scr["stage"] = "finalized"
    scr["finalized_at"] = core.now_jst()
    verify(scr, odds if odds is not None else core.load("odds_snapshots.json", []))
    _summ(scr)
    return scr


def verify(scr, odds):
    """最後にオッズを取得（ここで初めて市場を見る）。⑤-A/B の判定は変えず、市場との一致・不一致を別項目で記録。
    ⑤で確定していない試合で市場だけが極端なものは ⑤-C 市場だけ格差（⑤-A と混ぜない）。"""
    scr["odds_attached_at"] = core.now_jst()
    latest = {}
    for o in odds:
        if o.get("prices") and "L" in o["prices"] and "R" in o["prices"] and o.get("exact", True):
            if o["match_id"] not in latest or o["taken_at"] > latest[o["match_id"]]["taken_at"]:
                latest[o["match_id"]] = o
    for row in scr["rows"]:
        o = latest.get(row["match_id"])
        if not o or row.get("status") == "対象外":
            continue
        nv, _ = core.no_vig({k: v for k, v in o["prices"].items() if v})
        fav = "L" if nv["L"] >= nv["R"] else "R"
        mk = dict(taken_at=o["taken_at"], source=o["source"], prices=o["prices"], nv_fav=round(nv[fav], 4), fav=fav)
        if row.get("status") == "格差候補確定":
            mk.update(agrees=fav == row["side"], nv_side=round(nv[row["side"]], 4),
                      note="市場も同じ側を本命視" if fav == row["side"] else "市場は逆側を本命視（⑤の判定は変えない）")
            row["market"] = mk
        elif nv[fav] >= MARKET_C_NV:
            row["market"] = mk
            row["market_only"] = dict(grade="C", grade_label=GRADE_LABEL["C"],
                                      note=f"市場の本命勝率{nv[fav]*100:.0f}%だが独立データで十分確認できていない（⑤：{row.get('status')}）")


def _summ(scr):
    by = {}
    for r in scr["rows"]:
        s = by.setdefault(r.get("group") or r["sport"], dict(scanned=0, excluded=0, with_indicators=0, candidates=0, grade_a=0, grade_b=0,
                                                              held=0, incomplete=0, market_only=0))
        s["scanned"] += 1
        st = r.get("status")
        if st == "対象外":
            s["excluded"] += 1; continue
        if r.get("indicators_available"):
            s["with_indicators"] += 1
        if st in CAND:
            s["candidates"] += 1
        if st == "格差候補確定":
            s["grade_a" if r.get("grade") == "A" else "grade_b"] += 1
        s["held"] += st == "反対材料で保留"
        s["incomplete"] += st == "深掘り未完"
        s["market_only"] += bool(r.get("market_only"))
    for g, s in by.items():
        if s["grade_a"] + s["grade_b"] == 0:
            s["message"] = "本日はこの競技に明確な格差候補なし" if scr.get("stage") == "finalized" else (
                "一次候補なし（本日はこの競技に明確な格差候補なし）" if s["candidates"] == 0 else "一次候補あり・深掘り待ち")
    scr["by_sport"] = by


def tag_rows(rows, scr):
    """①〜④の判定行に⑤の結果を付ける（①〜④は従来どおり全試合を判定し、⑤候補は完全深掘りのうえ優先判定）。"""
    d = {r["match_id"]: r for r in scr.get("rows", [])}
    for r in rows:
        x = d.get(r["match_id"])
        if not x:
            continue
        if x.get("status") == "格差候補確定":
            r["d5"] = dict(grade=x["grade"], type=x.get("type_label"), side=x["side"])
        elif x.get("market_only"):
            r["d5"] = dict(grade="C")
        elif x.get("status") in CAND:
            r["d5"] = dict(status=x["status"])
    return rows


def save(scr):
    core.save("discovery/latest.json", scr)
    rid = re.sub(r"[^0-9]", "", scr["locked_at"])[:12]
    core.save(f"discovery/history/{rid}-{scr['stage']}.json", scr)


if __name__ == "__main__":
    cmd, locked = sys.argv[1], sys.argv[2]
    scr = run_screen(locked) if cmd == "screen" else run_finalize(locked)
    save(scr)
    for g, s in sorted(scr["by_sport"].items(), key=lambda kv: -kv[1]["scanned"]):
        print(g, s)
