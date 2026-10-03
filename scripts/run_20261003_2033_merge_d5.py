"""手動実行（10-03）：⑤ Tier1 深掘りサブエージェントの結果（/home/claude/dd/d5/<match_id>.json）を facts に統合する。
deep5・counter_evidence はサブエージェントの値を優先（Web確認済み）、unavailable・lineup・risks・source_urls は追記。facts が無い試合は facts_new から作る。"""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core
n = 0; log = []
for f in sorted(glob.glob("/home/claude/dd/d5/*.json")):
    p = json.load(open(f, encoding="utf-8"))
    mid = p["match_id"]
    fp = core.path("facts", f"{mid}.json")
    fx = json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else None
    if fx is None:
        fx = p.get("facts_new")
        if not fx:
            log.append((mid, "facts なし・facts_new なし")); continue
        fx["match_id"] = mid
    elif p.get("facts_new"):
        # 既存 facts がある場合は、facts_new の不足部分だけ補う（行データは既存優先）
        for k, v in p["facts_new"].items():
            if k not in fx or fx[k] in (None, "", [], {}):
                fx[k] = v
    dd = fx.setdefault("deep5", {})
    for k, v in (p.get("deep5") or {}).items():
        if v not in (None, "", [], {}):
            dd[k] = v
    ce = fx.setdefault("counter_evidence", {})
    for k, v in (p.get("counter_evidence") or {}).items():
        if isinstance(v, dict) and v.get("finding"):
            ce[k] = v
    un = fx.setdefault("unavailable", {})
    if isinstance(p.get("unavailable"), dict):
        for k, v in p["unavailable"].items():
            un.setdefault(k, v)
    for k in list(un):   # deep5 に値が入った項目の「取得できず」は外す
        for dk in ("goalie", "save_pct", "gsaa", "pp_pct", "pk_pct", "first_rate"):
            if k == dk and dd.get(dk):
                un.pop(k, None)
    for key in ("risks", "source_urls"):
        cur = fx.setdefault(key, [])
        for x in p.get(key) or []:
            if x not in cur:
                cur.append(x)
    side_l = fx.setdefault("left", {})
    lu = side_l.setdefault("lineup", [])
    for x in p.get("lineup") or []:
        if x not in lu:
            lu.append(x)
    if p.get("data_as_of") and (not fx.get("data_as_of") or p["data_as_of"] > fx["data_as_of"]):
        fx["data_as_of"] = p["data_as_of"]
    fx.setdefault("deep_dive_log", []).append(dict(run="run-20261003-2033", searches=p.get("searches"), heaviest_step=p.get("heaviest_step")))
    with open(fp, "w", encoding="utf-8") as fh:
        json.dump(fx, fh, ensure_ascii=False, indent=1); fh.write("\n")
    n += 1
print("merged", n, log)
