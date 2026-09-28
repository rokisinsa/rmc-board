"""data/bc/*.txt（BET CHANNEL prematch配信の控え）を読む。"""
import re

SPORTS = {  # sport_id: (RMC表示名, 区分)  区分 real=実チーム/選手のeスポーツ, sim=シミュレーション・バーチャル系, br=バトルロイヤル
    109: ("CS2", "real"), 110: ("LoL", "real"), 111: ("Dota 2", "real"), 115: ("World of Tanks", "real"),
    123: ("CrossFire", "real"), 125: ("Rainbow Six", "real"), 230: ("Standoff 2", "real"), 134: ("King of Glory", "real"), 194: ("VALORANT", "real"),
    201: ("Mobile Legends", "real"), 222: ("StarCraft: BW", "real"), 230: ("Standoff 2", "real"), 170: ("Fortnite", "br"),
    137: ("FC 26（eFootball）", "sim"), 153: ("NBA 2K26", "sim"), 238: ("Cricket 24", "sim"), 300: ("eサッカー", "sim"),
    302: ("eバスケットボール", "sim"), 303: ("eテニス", "sim"), 305: ("V-クリケット", "sim"), 309: ("eサッカー：ヴォルタ", "sim"),
    322: ("eクリケット", "sim"), 323: ("イバケジャダ（BET CHANNEL表記）", "sim"),
}
MARKET = {"186": "MatchWinner", "219": "MatchWinner（延長込み）", "11": "MatchWinner", "1": "1X2"}


def load(path):
    rows, prefix, taken = [], [], None
    for ln in open(path, encoding="utf-8"):
        ln = ln.rstrip("\n")
        if ln.startswith("# 取得"):
            taken = re.search(r"(\d{4}-\d\d-\d\dT[\d:]+\+09:00)", ln)[1]
        if ln.startswith("PREFIX "):
            for p in ln[7:].split(","):
                a, _, n = p.partition("*")
                prefix += [a] * int(n or 1)
            continue
        if not ln or ln.startswith("#"):
            continue
        suf, sp, comp, st, teams, mk, nm = ln.split("|")
        full = suf if len(suf) > 7 else None
        l, _, r = teams.partition("~")
        odds = None
        if mk:
            mid, _, o = mk.partition(":")
            v = [float(x) for x in o.split("/")]
            odds = dict(market_id=mid, market=MARKET.get(mid, mid), L=v[0], R=v[-1], D=v[1] if len(v) == 3 else None)
        rows.append(dict(suffix=suf[-7:], event_id=full, sport_id=int(sp), competition=comp, start_jst=f"{taken[:4]}-{st[:5]}T{st[6:]}:00+09:00",
                         left=l.strip(), right=r.strip(), odds=odds, market_count=int(nm), outright=(r.strip() == "Winner" or int(sp) == 170)))
    if prefix:
        assert len(prefix) == len(rows), (len(prefix), len(rows))
        for x, p in zip(rows, prefix):
            x["event_id"] = p + x["suffix"]
    else:
        assert all(x["event_id"] for x in rows), "v2形式はevent_id全桁必須"
    return taken, rows
