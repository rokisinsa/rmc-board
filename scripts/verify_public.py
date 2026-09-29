"""公開RMCの実データ確認（チェックリスト36〜39）。GitHub Actions の deploy 直後に無人で実行する。
1. 公開 data/deploy.json の sha が今回のコミットになるまで待つ（最大10分、cache bust 付き）
2. index.html と data 配下の全JSONを公開URLから取り直し、リポジトリの同じファイルとバイト一致を確認（古いJS/JSONが残っていないか）
3. 公開JSONだけから①〜④・経験値取引の収支、格差スコア帯別、CLV等を再計算し、公開 summary.json と一致するか確認
4. 公開 summary.run_id が公開 automation-runs の最新 run_id と一致するか確認
結果を標準出力にJSONで出し、1つでも失敗なら終了コード1（＝Actions失敗）。"""
import glob, json, os, sys, tempfile, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core

BASE = "https://rokisinsa.github.io/rmc-board/"
ROOT = core.ROOT
SHA = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_SHA", "")


def get(rel):
    url = f"{BASE}{rel}{'&' if '?' in rel else '?'}cb={int(time.time()*1000)}"
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache", "User-Agent": "rmc-verify"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read()


def main():
    rep = dict(sha=SHA, checks={}, errors=[])
    # 36: 最新コミットが公開されたか
    ok = False
    for _ in range(40):
        try:
            st, body = get("data/deploy.json")
            if st == 200 and json.loads(body).get("sha") == SHA:
                ok = True; break
        except Exception as e:
            rep["last_error"] = str(e)[:200]
        time.sleep(15)
    rep["checks"]["36_pages_sha"] = ok
    if not ok:
        rep["errors"].append("公開 deploy.json の sha が今回のコミットにならない")
    # 39: 公開ファイルとリポジトリの一致（index.html と data 配下）
    files = ["index.html"] + sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "data", "**", "*.json"), recursive=True)
                                   if "/snapshots/" not in p and "/deploys/" not in p and not p.endswith("data/deploy.json"))
    tmp = tempfile.mkdtemp()
    mism = []
    for rel in files:
        try:
            st, body = get(rel)
        except Exception as e:
            mism.append(f"{rel}: 取得失敗 {e}"); continue
        local = open(os.path.join(ROOT, rel), "rb").read()
        if body != local:
            mism.append(f"{rel}: 公開内容がリポジトリと不一致")
        if rel.startswith("data/"):
            dst = os.path.join(tmp, rel[5:]); os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "wb").write(body)
    rep["checks"]["39_files_match"] = not mism
    rep["files_checked"] = len(files)
    rep["errors"] += mism[:20]
    # 37・38: 公開JSONだけで再計算
    core.DATA = tmp
    try:
        matches = core.load("matches.json", {})
        odds = core.load("odds_snapshots.json", [])
        led = {lg: core.load(f"ledger/{lg}.json", []) for lg in core.LOGICS + ("experience",)}
        pub = core.load("summary.json", {})
        logics = {lg: core.summarize(led[lg], matches) for lg in led}
        bt = {lg: {t: core.summarize([e for e in led[lg] if (e.get("pick_type") or "criteria") == t], matches) for t in ("criteria", "sport_floor")} for lg in led}
        ok38 = pub.get("by_type") == bt and pub.get("logics") == logics and pub.get("gap_bands") == core.gap_bands(led, odds) and pub.get("analytics") == core.analytics(led, matches, odds, core.load("odds_closing.json", []))
        runs = core.load("automation-runs.json", [])
        ok37 = bool(runs) and pub.get("run_id") == runs[-1].get("run_id")
    except Exception as e:
        ok37 = ok38 = False; rep["errors"].append(f"再計算失敗: {e}")
    rep["checks"]["37_public_json_run_id"] = ok37
    rep["checks"]["38_public_profit_recompute"] = ok38
    if not ok37: rep["errors"].append("公開 summary.run_id が公開 automation-runs の最新と不一致")
    if not ok38: rep["errors"].append("公開JSONからの収支再計算が公開 summary.json と不一致")
    rep["ok"] = all(rep["checks"].values())
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
