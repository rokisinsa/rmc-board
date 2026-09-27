"""data/facts/*.json の行データから集計（calc）を計算して書き込む。集計は手書きせず必ずここで出す。"""
import glob, json, os, re
from datetime import date
from . import core

RECENT_DAYS = 50  # 共通の対戦相手は試合日から50日以内の結果だけで比較する


def _norm(name):
    s = re.sub(r"[（(].*?[）)]", "", str(name or ""))
    s = re.sub(r"\s|　|・|FC|CF|W$|U\d\d", "", s)
    return s.lower()


def _pts(score, res=None):
    """スコア文字列から (自分/左, 相手/右) の点数を取り出す。勝敗と矛盾する並びは入れ替え、判断できなければ None。"""
    m = re.search(r"(\d+)\s*[-–:：]\s*(\d+)", str(score or ""))
    if not m:
        return None
    a, b = int(m[1]), int(m[2])
    if res in ("W", "left") and a < b or res in ("L", "right") and a > b:
        a, b = b, a
    if res in ("D", "draw") and a != b:
        return None
    return a, b


def _inner(detail, a_units, b_units):
    """セット別スコア（例 '25-20 23-25 25-18' / '6-4 3-6 7-6(5)'）から中身の点数（ゲーム数・ラリー点）の合計を出す。
    セット勝敗が units と一致する向きのときだけ採用する。"""
    if not isinstance(a_units, (int, float)) or not isinstance(b_units, (int, float)):
        return None
    txt = re.sub(r"\(\d+\)", "", str(detail or ""))
    pairs = [(int(x), int(y)) for x, y in re.findall(r"(?<![\d.])(\d{1,2})\s*-\s*(\d{1,2})(?![\d.])", txt)]
    if len(pairs) < 2 or len(pairs) != a_units + b_units:
        return None
    wa = sum(1 for x, y in pairs if x > y); wb = sum(1 for x, y in pairs if y > x)
    sa = sum(x for x, _ in pairs); sb = sum(y for _, y in pairs)
    if (wa, wb) == (a_units, b_units):
        return sa, sb
    if (wb, wa) == (a_units, b_units):
        return sb, sa
    return None


def _side_calc(side):
    f = side.get("form") or []
    rec = {"W": 0, "L": 0, "D": 0}
    ha = {"H": {"W": 0, "L": 0, "D": 0}, "A": {"W": 0, "L": 0, "D": 0}, "N": {"W": 0, "L": 0, "D": 0}}
    uw = ul = 0
    pf = pa = pn = 0
    ifor = iag = inn = 0
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
        p = _pts(g.get("score"), r)
        if p:
            pf += p[0]; pa += p[1]; pn += 1
        q = _inner(g.get("detail"), g.get("units_won"), g.get("units_lost"))
        if q:
            ifor += q[0]; iag += q[1]; inn += 1
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
    if pn:
        out.update(points_for=pf, points_against=pa, points_games=pn)
    if inn:
        out.update(inner_for=ifor, inner_against=iag, inner_games=inn)
    return out


def _h2h_calc(h2h):
    rec = {"left": 0, "right": 0, "draw": 0}
    ul = ur = 0
    pl = pr = pn = 0
    il = ir = inn = 0
    has_units = False
    for g in h2h or []:
        w = g.get("winner")
        if w in rec:
            rec[w] += 1
        p = _pts(g.get("score"), w)
        if p:
            pl += p[0]; pr += p[1]; pn += 1
        q = _inner(g.get("detail"), g.get("units_left"), g.get("units_right"))
        if q:
            il += q[0]; ir += q[1]; inn += 1
        if isinstance(g.get("units_left"), (int, float)) and isinstance(g.get("units_right"), (int, float)):
            ul += g["units_left"]; ur += g["units_right"]; has_units = True
    out = dict(games=sum(rec.values()), left=rec["left"], right=rec["right"], draw=rec["draw"])
    if has_units:
        out.update(units_left=ul, units_right=ur)
    if pn:
        out.update(points_left=pl, points_right=pr, points_games=pn,
                   avg_left=round(pl / pn, 1), avg_right=round(pr / pn, 1))
    if inn:
        out.update(inner_left=il, inner_right=ir, inner_games=inn)
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
                {"date": g.get("date"), "iso": str(gd), "score": g.get("score"), "res": g.get("res")})
    # 相手どうしの直接対戦は共通相手から除く
    ln, rn = _norm(left.get("name")), _norm(right.get("name"))
    rows = []
    for k, v in by.items():
        if v["left"] and v["right"] and k not in (ln, rn):
            lw = sum(1 for x in v["left"] if x["res"] == "W"); rw = sum(1 for x in v["right"] if x["res"] == "W")
            lt = len(v["left"]); rt = len(v["right"])
            edge = "left" if lw / lt > rw / rt else "right" if rw / rt > lw / lt else "even"
            basis = "勝率"
            if edge == "even":  # 勝率が同じなら1試合あたりの得失差で比べる
                def md(lst):
                    ps = [_pts(x["score"], x["res"]) for x in lst]
                    ps = [p for p in ps if p]
                    return sum(a - b for a, b in ps) / len(ps) if ps else None
                ml, mr = md(v["left"]), md(v["right"])
                if ml is not None and mr is not None and ml != mr:
                    edge = "left" if ml > mr else "right"; basis = "得失差"
            v["left"].sort(key=lambda x: x["iso"], reverse=True); v["right"].sort(key=lambda x: x["iso"], reverse=True)
            latest = max([x["iso"] for x in v["left"] + v["right"]])
            rows.append(dict(v, edge=edge, basis=basis if edge != "even" else None, latest=latest))
    rows.sort(key=lambda r: r["latest"], reverse=True)  # 直近の対戦ほど上
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
