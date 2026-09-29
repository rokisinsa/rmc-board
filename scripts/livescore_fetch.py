"""⑤ 格差候補発見エンジン用：オッズを使わない日程と基本指標を LiveScore 公開API から取得して data/basic/livescore.json に保存。
- 日程：今日・明日・明後日（JST）のサッカー・アイスホッケー・バスケットボール・クリケットの全試合（オッズ配信に無い試合も含む）
- 基本指標：各大会ステージの順位表（試合数・勝分敗・得失点・勝点）と、そのステージの消化済み試合の結果
GitHub Actions から実行（PCオフで動く）。オッズは取得しない。"""
import datetime as dt, gzip, json, os, sys, time, urllib.request

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "basic")
JST = dt.timezone(dt.timedelta(hours=9))
B = "https://prod-public-api.livescore.com/v1/api/app"
HDR = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Accept-Encoding": "gzip"}
SPORTS = {"soccer": "サッカー", "hockey": "アイスホッケー", "basketball": "バスケットボール", "cricket": "クリケット"}


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=30) as r:
                b = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    b = gzip.decompress(b)
                return json.loads(b.decode("utf-8", "replace"))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def jst(esd):
    s = str(esd)
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:00+09:00"


def team(e, k):
    t = (e.get(k) or [{}])[0]
    return t.get("Nm")


def score(e):
    a, b = e.get("Tr1"), e.get("Tr2")
    return (int(a), int(b)) if str(a).isdigit() and str(b).isdigit() else None


def main():
    os.makedirs(OUT, exist_ok=True)
    now = dt.datetime.now(JST)
    fixtures, stages, errors = [], {}, []
    for sp, jp in SPORTS.items():
        for add in (0, 1, 2):   # 今日・明日・明後日（⑤の走査窓48時間を覆う）
            d = (now + dt.timedelta(days=add)).strftime("%Y%m%d")
            try:
                day = get(f"{B}/date/{sp}/{d}/9?countryCode=JP&locale=en&MD=1")
            except Exception as e:
                errors.append(f"{sp} {d}: {type(e).__name__}: {e}"[:200]); continue
            for st in day.get("Stages", []):
                key = f"{sp}/{st.get('Ccd')}/{st.get('Scd')}"
                for e in st.get("Events", []):
                    if not team(e, "T1") or not team(e, "T2"):
                        continue
                    fixtures.append(dict(sport=jp, ls_sport=sp, eid=e.get("Eid"), competition=f"{st.get('Cnm')} / {st.get('Snm')}",
                                         stage=key, start_jst=jst(e.get("Esd")), t1=team(e, "T1"), t2=team(e, "T2"),
                                         status=e.get("Eps"), score=score(e)))
                stages.setdefault(key, None)
            time.sleep(1)
    for key in list(stages):
        sp, ccd, scd = key.split("/", 2)
        try:
            x = get(f"{B}/stage/{sp}/{ccd}/{scd}/9?locale=en&MD=1")
        except Exception as e:
            stages[key] = dict(error=f"{type(e).__name__}: {e}"[:200]); continue
        st = (x.get("Stages") or [{}])[0]
        table = {}
        for lt in ((st.get("LeagueTable") or {}).get("L") or []):
            for tb in lt.get("Tables") or []:
                for t in tb.get("team") or []:
                    table[t.get("Tnm")] = dict(rank=t.get("rnk"), played=t.get("pld"), W=t.get("win"), D=t.get("drw"),
                                               L=t.get("lst"), gf=t.get("gf"), ga=t.get("ga"), pts=t.get("pts"), group=tb.get("name"))
        results = []
        for e in st.get("Events") or []:
            sc = score(e)
            if sc and e.get("Eps") in ("FT", "AET", "AP", "OT", "Pen.", "AOT", "SO"):
                results.append(dict(date=jst(e.get("Esd"))[:10], t1=team(e, "T1"), t2=team(e, "T2"), s1=sc[0], s2=sc[1], status=e.get("Eps")))
        stages[key] = dict(name=f"{st.get('Cnm')} / {st.get('Snm')}", table=table, results=results)
        time.sleep(0.7)
    out = dict(taken_at=now.isoformat(timespec="seconds"), source="LiveScore 公開API（日程・順位表・結果。オッズは含まない）",
               fixtures=fixtures, stages=stages, errors=errors)
    json.dump(out, open(os.path.join(OUT, "livescore.json"), "w"), ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(dict(fixtures=len(fixtures), stages=len(stages), with_table=sum(1 for v in stages.values() if v and v.get("table")),
                          errors=errors[:5]), ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
