"""RMC内製の独立勝率モデル（オッズを使わない）。
log5法：各チームの直近シリーズ勝率をラプラス補正 (W+1)/(N+2) して、pA = a(1-b) / (a(1-b) + b(1-a))。
相手の強さを補正しない粗いモデルなので、②では幅を±0.08に広げ、④では信頼度を medium 以下に抑えて使う。"""

MIN_GAMES = 5
METHOD = "RMC log5（直近シリーズ勝率・ラプラス補正、data/facts の行データから計算）"


def log5(facts):
    out = {}
    for side in ("left", "right"):
        f = [g for g in ((facts.get(side) or {}).get("form") or []) if g.get("res") in ("W", "L", "D")]
        if len(f) < MIN_GAMES:
            return None, f"{(facts.get(side) or {}).get('name', side)}の直近成績が{len(f)}試合しかない（{MIN_GAMES}試合未満）"
        w = sum(1 for g in f if g["res"] == "W") + 0.5 * sum(1 for g in f if g["res"] == "D")
        out[side] = ((w + 1) / (len(f) + 2), len(f), w)
    a, b = out["left"][0], out["right"][0]
    p = a * (1 - b) / (a * (1 - b) + b * (1 - a))
    return dict(prob=round(p, 4), side="L", method=METHOD,
                inputs=f"左 {out['left'][2]:g}勝/{out['left'][1]}試合→{a:.3f}、右 {out['right'][2]:g}勝/{out['right'][1]}試合→{b:.3f}"), None
