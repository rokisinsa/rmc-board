"""締切前オッズの記録（CLV用）。GitHub Actions odds-fetch が毎時、配信取得の直後に実行する（無人・PCオフで動く）。
未精算の正式採用がある試合のうち、まだ始まっていないものについて、最新の公開配信から同じ試合・同じブックの
現在オッズを data/odds_closing.json に追記する（定時更新の odds_snapshots.json とは別ファイルにして書き込み競合を避ける）。試合開始前で最後に記録された値が締切オッズ（closing）になる。
試合の対応づけは、定時更新が記録したスナップショットの配信ID（bov:<id>／te:<id>）で行い、名前の推測はしない。"""
import datetime as dt, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core

JST = dt.timezone(dt.timedelta(hours=9))


def orient(two, last):
    """配信の2値 (a, b) を既存スナップショット last{L,R} と同じ向きにそろえる。近い値の差が小さく判別できなければ None。"""
    a, b = two
    d1 = abs(a - last["L"]) / last["L"] + abs(b - last["R"]) / last["R"]
    d2 = abs(b - last["L"]) / last["L"] + abs(a - last["R"]) / last["R"]
    if abs(d1 - d2) < 0.15:   # 両向きの差がほぼ同じ（五分の試合）なら向きを決めない
        return None
    return (a, b) if d1 < d2 else (b, a)


def main():
    now = dt.datetime.now(JST)
    matches = core.load("matches.json", {})
    odds = core.load("odds_snapshots.json", [])
    closing = core.load("odds_closing.json", [])
    pend = set()
    for lg in core.LOGICS + ("experience",):
        for e in core.load(f"ledger/{lg}.json", []):
            if not e.get("result") and not e.get("withdrawn"):
                pend.add(e["match_id"])
    bov = core.load("odds_feed/bovada.json", {}) or {}
    ten = core.load("odds_feed/tennis.json", {}) or {}
    bov_by = {str(ev.get("id")): ev for ev in bov.get("events") or []}
    ten_by = {str(m.get("id")): m for m in ten.get("matches") or []}
    added = 0
    for mid in sorted(pend):
        m = matches.get(mid)
        if not m or core.parse(m["start_jst"]) <= now:
            continue
        snaps = [o for o in odds if o["match_id"] == mid and o.get("prices") and "L" in o["prices"] and "R" in o["prices"]]
        for o in sorted(snaps, key=lambda o: o["taken_at"], reverse=True):
            s = o["source"]
            bid = re.search(r"bov:(\d+)", s)
            tid = re.search(r"te:(\d+)", s)
            new = None
            if bid and bid[1] in bov_by and (bov_by[bid[1]].get("market") or {}).get("outcomes"):
                oc = [x for x in bov_by[bid[1]]["market"]["outcomes"] if (x.get("type") or "") != "D" and (x.get("name") or "").lower() != "draw"]
                if len(oc) == 2:
                    ab = orient((oc[0]["dec"], oc[1]["dec"]), o["prices"])
                    if ab:
                        new = dict(src=f"Bovada（公開coupon JSON・{bov['taken_at'][11:16]}取得・bov:{bid[1]}・締切前記録）",
                                   taken=bov["taken_at"], L=ab[0], R=ab[1], market=o.get("market"))
            elif tid and tid[1] in ten_by:
                book = s.split("（")[0]
                bk = (ten_by[tid[1]].get("books") or {}).get(book)
                if bk:
                    ab = orient((bk[0], bk[1]), o["prices"])
                    if ab:
                        new = dict(src=f"{book}（tennisexplorer経由・{ten['taken_at'][11:16]}取得・te:{tid[1]}・締切前記録）",
                                   taken=ten["taken_at"], L=ab[0], R=ab[1], market=o.get("market"))
            if new:
                taken = new["taken"]
                if core.parse(taken) < core.parse(m["start_jst"]) and not any(
                        x["match_id"] == mid and x["source"] == new["src"] and x["taken_at"] == taken for x in closing):
                    closing.append(dict(match_id=mid, taken_at=taken, source=new["src"], market=new["market"],
                                     prices={"L": round(new["L"], 3), "R": round(new["R"], 3)}, exact=True, book_verified=False, kind="pre_close"))
                    added += 1
                break
    core.save("odds_closing.json", closing)
    print(json.dumps(dict(at=now.isoformat(timespec="seconds"), pending_matches=len(pend), added=added), ensure_ascii=False))


if __name__ == "__main__":
    main()
