"""06:00枠（10-02）：公開配信（bovada.json・tennis.json）から判定時刻〜48時間の試合を展開し、既存試合へ対応づけ（feed_id→名前照合）、
未登録は matches に登録、単一ブックの exact odds を odds_snapshots に追記（⑤の母集団用。⑤の候補発見はオッズを使わない）。
run_20260929_1800_feed.py / _mapping.py / run_20260929_1800.py の取り込み部を雛形にした。使い方: python scripts/run_20261002_0600_ingest.py <基準時刻JST> [--no-new]"""
import json, hashlib, sys, re, os, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmc import core
from rmc.oddsfeed import _n as _n0
LOCK = sys.argv[1]
NO_NEW = "--no-new" in sys.argv   # 再取得した配信で既存の試合のオッズだけ更新（⑤の母集団を確定後に新規試合を足さない）
DD = "/home/claude/dd"
H48 = core.parse(LOCK).timestamp() + 48 * 3600
b = core.load('odds_feed/bovada.json'); t = core.load('odds_feed/tennis.json')
SP = {'hockey': 'アイスホッケー', 'soccer': 'サッカー', 'basketball': 'バスケットボール', 'baseball': '野球', 'darts': 'ダーツ', 'snooker': 'スヌーカー',
      'badminton': 'バドミントン', 'table-tennis': '卓球', 'volleyball': 'バレーボール', 'cricket': 'クリケット', 'handball': 'ハンドボール', 'football': 'アメフト',
      'rugby-union': 'ラグビー', 'rugby-league': 'ラグビーリーグ', 'aussie-rules': 'オージーボール', 'ufc-mma': 'MMA', 'boxing': 'ボクシング', 'futsal': 'フットサル'}
ES = {'Counter-Strike 2': 'CS2', 'Dota 2': 'Dota 2', 'League Of Legends': 'LoL', 'Rainbow Six': 'Rainbow Six', 'Valorant': 'VALORANT', 'King of Glory': 'King of Glory'}
def nid(fid, st): return "m" + st[:10].replace('-', '') + "-" + hashlib.sha1(fid.encode()).hexdigest()[:8]
out = []; skipped = []
for e in b['events']:
    fid = 'bov:' + str(e['id'])
    if e['sport'] == 'tennis': skipped.append((fid, 'テニスはtennisexplorer（ブック別）を使用')); continue
    if 'Series' in e['league'] or 'Futures' in e['league'] or 'Specials' in e['league']: skipped.append((fid, 'シリーズ勝者/先物/特別市場（単一試合でない）')); continue
    if e['start_jst'] <= LOCK or core.parse(e['start_jst']).timestamp() > H48: continue
    if e.get('live'): continue
    sp = ES.get(e['league'].split(' / ')[0], 'eスポーツ（その他）') if e['sport'] == 'esports' else SP.get(e['sport'], e['sport'])
    mk = e.get('market'); prices = None; left = right = None
    if mk:
        oc = mk['outcomes']; two = [o for o in oc if (o.get('type') or '') != 'D' and (o.get('name') or '').lower() != 'draw']
        if len(two) == 2:
            prices = {'L': round(two[0]['dec'], 3), 'R': round(two[1]['dec'], 3)}
            d = [o for o in oc if o not in two]
            if d: prices['D'] = round(d[0]['dec'], 3)
            left, right = two[0]['name'], two[1]['name']
    if not prices:
        tm = [x['name'] for x in e.get('teams') or []]
        parts = re.split(r'\s+(?:vs\.?|@|v)\s+', e['desc'] or '')
        left, right = (parts + [None, None])[:2] if len(parts) >= 2 else (tm + [None, None])[:2]
    if not left or not right: skipped.append((fid, '対戦カードが2者でない')); continue
    out.append(dict(fid=fid, sport=sp, league=e['league'], start_jst=e['start_jst'], left=left, right=right, desc=e['desc'],
                    at=' @ ' in (e['desc'] or ''), prices=prices, book='Bovada', src='Bovada', taken_at=b['taken_at'], market=(mk or {}).get('market') or 'Moneyline',
                    new_id=nid(fid, e['start_jst']), books=None))
for e in t['matches']:
    fid = 'te:' + str(e['id'])
    if e['start_jst'] <= LOCK or core.parse(e['start_jst']).timestamp() > H48: continue
    pk = e.get('pick')
    out.append(dict(fid=fid, sport='テニス', league=e['tournament'], start_jst=e['start_jst'], left=e['p1'], right=e['p2'], desc=None, at=False,
                    prices={'L': pk['L'], 'R': pk['R']} if pk else None, book=pk['book'] if pk else None, src='tennisexplorer', taken_at=t['taken_at'],
                    market='Match Winner（2way）', new_id=nid(fid, e['start_jst']), books=e.get('books'), names_full=e.get('names_full')))
json.dump(out, open(f'{DD}/feed_inv.json', 'w'), ensure_ascii=False, indent=0)
json.dump(skipped, open(f'{DD}/feed_skipped.json', 'w'), ensure_ascii=False)
print('feed', len(out), collections.Counter(x['sport'] for x in out), 'priced', sum(1 for x in out if x['prices']))

# ---- 対応づけ（run_20260929_1800_mapping.py と同じ）----
STOP = {'u19', 'u21', 'u20', 'u23', 'u17', 'town', 'city', 'united', 'utd', 'de', 'les', 'women', 'sc', 'ac', 'cf', 'fk', 'jk', 'sk', 'hc', 'bk', 'if', 'real', 'sporting', 'athletic', 'ii', 'reserves', 'the', 'and', 'of', 'la', 'le', 'del', 'st'}
def _n(s): return _n0(s) - STOP
matches = core.load('matches.json'); odds = core.load('odds_snapshots.json')
byfid = {}
for mid, x in matches.items():
    for f in x.get('feed_ids', []): byfid[f] = mid
mapping = []
for x in out:
    if x['fid'] in byfid:
        mid = byfid[x['fid']]; mm = matches[mid]
        sw = bool(_n(mm['left']) & _n(x['right']) and not _n(mm['left']) & _n(x['left']))
        mapping.append(dict(fid=x['fid'], match_id=mid, swapped=sw, how='feed_id')); continue
    t0 = core.parse(x['start_jst']).timestamp()
    for mid, mm in matches.items():
        if mm['status'] not in ('scheduled', 'unknown') or mm['sport'] != x['sport'] or abs(core.parse(mm['start_jst']).timestamp() - t0) > 3 * 3600: continue
        L, R = _n(mm['left']), _n(mm['right']); a, bb = _n(x['left']), _n(x['right'])
        if L & a and R & bb: mapping.append(dict(fid=x['fid'], match_id=mid, swapped=False, how='name')); break
        if L & bb and R & a: mapping.append(dict(fid=x['fid'], match_id=mid, swapped=True, how='name')); break
json.dump(mapping, open(f'{DD}/mapping.json', 'w'), ensure_ascii=False, indent=0)
mp = {x['fid']: x for x in mapping}

# ---- 登録・オッズ追記（run_20260929_1800.py の取り込み部と同じ）----
def clean(n): return re.sub(r"\s*\(\d+\)\s*$", "", str(n)).strip()
def norm(n): return re.sub(r"[^a-z]", "", clean(n).lower())
fid2mid, fid_swapped, seen, dup = {}, {}, {}, []
have_odds = {(o['match_id'], o['taken_at']) for o in odds}
for x in out:
    key = (x["sport"], x["start_jst"][:10], frozenset((norm(x["left"]), norm(x["right"]))))
    m_ = mp.get(x["fid"])
    if key in seen and not m_:
        dup.append((x["fid"], seen[key])); continue
    if m_:
        mid = m_["match_id"]; fid_swapped[x["fid"]] = bool(m_.get("swapped"))
    else:
        mid = x["new_id"]
    if NO_NEW and mid not in matches:
        dup.append((x["fid"], "⑤確定後の再取得で初出の試合（次回の定時更新で走査）")); continue
    seen[key] = x["fid"]; fid2mid[x["fid"]] = mid
    if mid in matches:
        m = matches[mid]
        m.setdefault("feed_ids", [])
        if x["fid"] not in m["feed_ids"]: m["feed_ids"].append(x["fid"])
        if m["status"] == "scheduled" and m["start_jst"] != x["start_jst"] and x["start_jst"] > LOCK:
            m["note"] = (m.get("note") or "") + f"／開始時刻を配信{x['fid']}（{x['taken_at'][11:16]}取得）の{x['start_jst'][5:16]}に更新（旧{m['start_jst'][5:16]}）"
            m["start_jst"] = x["start_jst"]
    else:
        team = x["sport"] not in ("テニス", "ダーツ", "スヌーカー", "バドミントン", "MMA", "ボクシング")
        matches[mid] = dict(sport=x["sport"], competition=x["league"], round=None, start_jst=x["start_jst"], left=clean(x["left"]), right=clean(x["right"]),
                            home_away=("右＝ホーム（配信の「@」表記・左＝アウェイ）" if x.get("at") else "左＝ホーム（配信表記）") if team else "中立（大会会場）",
                            status="scheduled", result=None, note=f"{x['src']} {x['fid']}（{x['taken_at'][11:16]}取得）", flags=[], feed_ids=[x["fid"]])
    if x["prices"] and (mid, x["taken_at"]) not in have_odds:
        p = dict(x["prices"])
        if fid_swapped.get(x["fid"]): p["L"], p["R"] = p["R"], p["L"]
        via = "Bovada 公開coupon JSON" if x["src"] == "Bovada" else "tennisexplorer経由（ブック別オッズ）"
        odds.append(dict(match_id=mid, taken_at=x["taken_at"], source=f"{x['book']}（{via}・{x['taken_at'][11:16]}取得・{x['fid']}）",
                         market=x["market"], prices=p, exact=True, book_verified=False))
        have_odds.add((mid, x["taken_at"]))
core.save('matches.json', matches); core.save('odds_snapshots.json', odds)
json.dump(dict(fid2mid=fid2mid, fid_swapped=fid_swapped, dup=dup), open(f'{DD}/ingest.json', 'w'), ensure_ascii=False)
print('mapped', len(mapping), 'registered/linked', len(fid2mid), 'dup', len(dup))
