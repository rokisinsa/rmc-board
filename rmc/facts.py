"""data/facts/*.json の行データから集計（calc）を計算して書き込む。集計は手書きせず必ずここで出す。"""
import glob, json, os, re
from datetime import date
from . import core

RECENT_DAYS = 30  # 共通の対戦相手は試合日から30日以内（約1か月）の結果だけで比較する


def _norm(name):
    s = re.sub(r"[（(].*?[）)]", "", str(name or ""))
    s = re.sub(r"\s|　|・|FC|CF|W$|U\d\d", "", s)
    return s.lower()


def _side_calc(side):
    f = side.get("form") or []
    rec = {"W": 0, "L": 0, "D": 0}
    ha = {"H": {"W": 0, "L": 0, "D": 0}, "A": {"W": 0, "L": 0, "D": 0}, "N": {"W": 0, "L": 0, "D": 0}}
    uw = ul = 0
    has_units = False
    streak_res, streak_n = None, 0
    for i, g in enumerate(f):
        r = g.get("res")
        if r not in rec:
            continue
        rec[r] += 1
        if g.get("ha") in ha:
            ha[g["ha"]][r] += 1
        if isinstance(g.get("units_won"), (int, float)) and isinstance(g.get("units_lost"), (int, float)):
            uw += g["units_won"]; ul += g["units_lost"]; has_units = True
        if i == 0:
            streak_res, streak_n = r, 1
        elif r == streak_res and streak_n == i:
            streak_n += 1
    n = sum(rec.values())
    out = dict(games=n, W=rec["W"], L=rec["L"], D=rec["D"],
               win_rate=round(rec["W"] / n * 100, 1) if n else None,
               home={k: v for k, v in ha["H"].items()}, away={k: v for k, v in ha["A"].items()},
               streak=(f"{streak_n}連{'勝' if streak_res == 'W' else '敗' if streak_res == 'L' else '分'}" if streak_n >= 2 else None))
    if has_units:
        out.update(units_won=uw, units_lost=ul)
    return out


def _h2h_calc(h2h):
    rec = {"left": 0, "right": 0, "draw": 0}
    ul = ur = 0
    has_units = False
    for g in h2h or []:
        w = g.get("winner")
        if w in rec:
            rec[w] += 1
        if isinstance(g.get("units_left"), (int, float)) and isinstance(g.get("units_right"), (int, float)):
            ul += g["units_left"]; ur += g["units_right"]; has_units = True
    out = dict(games=sum(rec.values()), left=rec["left"], right=rec["right"], draw=rec["draw"])
    if has_units:
        out.update(units_left=ul, units_right=ur)
    return out


def _parse(d, ref):
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", str(d or ""))
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"^(\d{1,2})/(\d{1,2})$", str(d or ""))
    if m and ref:  # 年なしは試合日以前で最も近い日付とみなす
        y = ref.year if (int(m[1]), int(m[2])) <= (ref.month, ref.day) else ref.year - 1
        return date(y, int(m[1]), int(m[2]))
    return None


def _common(left, right, ref=None):
    lf, rf = left.get("form") or [], right.get("form") or []
    by = {}
    for side, form in (("left", lf), ("right", rf)):
        for g in form:
            gd = _parse(g.get("date"), ref)
            if ref is None or gd is None or (ref - gd).days > RECENT_DAYS or gd > ref:
                continue
            k = _norm(g.get("opp"))
            if not k or k in ("—", "-"):
                continue
            by.setdefault(k, {"opp": g.get("opp"), "left": [], "right": []})[side].append(
                {"date": g.get("date"), "score": g.get("score"), "res": g.get("res")})
    # 相手どうしの直接対戦は共通相手から除く
    ln, rn = _norm(left.get("name")), _norm(right.get("name"))
    rows = []
    for k, v in by.items():
        if v["left"] and v["right"] and k not in (ln, rn):
            lw = sum(1 for x in v["left"] if x["res"] == "W"); rw = sum(1 for x in v["right"] if x["res"] == "W")
            lt = len(v["left"]); rt = len(v["right"])
            edge = "left" if lw / lt > rw / rt else "right" if rw / rt > lw / lt else "even"
            rows.append(dict(v, edge=edge))
    return rows


def enrich(x, start=None):
    ref = _parse(start, None) if start else None
    x["calc"] = dict(left=_side_calc(x.get("left") or {}), right=_side_calc(x.get("right") or {}),
                     h2h=_h2h_calc(x.get("h2h")), common=_common(x.get("left") or {}, x.get("right") or {}, ref),
                     common_window_days=RECENT_DAYS, common_ref_date=str(ref) if ref else None)
    return x


def enrich_all():
    n = 0
    matches = core.load("matches.json", {})
    for f in sorted(glob.glob(os.path.join(core.DATA, "facts", "*.json"))):
        x = json.load(open(f, encoding="utf-8"))
        enrich(x, (matches.get(x.get("match_id")) or {}).get("start_jst"))
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(x, fh, ensure_ascii=False, indent=1); fh.write("\n")
        n += 1
    return n
