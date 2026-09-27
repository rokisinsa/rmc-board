"""台帳から summary.json を再生成する（公開ページとprofit auditが読む唯一の集計値）。
使い方: python -m rmc.build"""
from .core import load, save, summarize, LOGICS, now_jst


def build():
    from .facts import enrich_all
    enrich_all()
    matches = load("matches.json", {})
    runs = load("automation-runs.json", [])
    logics = {lg: summarize(load(f"ledger/{lg}.json", []), matches) for lg in LOGICS + ("experience",)}
    last = runs[-1] if runs else {}
    out = {
        "run_id": last.get("run_id"),
        "run_status": last.get("status"),
        "built_at": now_jst(),
        "logics": logics,
    }
    save("summary.json", out)
    return out


if __name__ == "__main__":
    s = build()
    for k, v in s["logics"].items():
        print(k, f"{v['formal']}件 {v['win']}勝{v['loss']}敗 pending{v['pending']} 純損益{v['net']} ROI{v['roi']}")
