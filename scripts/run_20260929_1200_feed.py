"""12:00枠（09-29）：公開配信（bovada.json・tennis.json）から今後24時間の試合を1行ずつに展開（/home/claude/dd/feed_inv.json）。Bovadaテニスは tennisexplorer と重複するため除外、シリーズ勝者市場は単一試合でないため除外。使い方: python scripts/run_20260929_0600_feed.py <ロック時刻JST>"""
import json,hashlib,sys,re
sys.path.insert(0,'/home/claude/rmc-board')
from rmc import core
LOCK=sys.argv[1]
H24=core.parse(LOCK).timestamp()+24*3600
b=core.load('odds_feed/bovada.json'); t=core.load('odds_feed/tennis.json')
SP={'hockey':'アイスホッケー','soccer':'サッカー','basketball':'バスケットボール','baseball':'野球','darts':'ダーツ','snooker':'スヌーカー',
    'badminton':'バドミントン','table-tennis':'卓球','volleyball':'バレーボール','cricket':'クリケット','handball':'ハンドボール','football':'アメフト',
    'rugby-union':'ラグビー','rugby-league':'ラグビーリーグ','aussie-rules':'オージーボール','ufc-mma':'MMA','boxing':'ボクシング','futsal':'フットサル'}
ES={'Counter-Strike 2':'CS2','Dota 2':'Dota 2','League Of Legends':'LoL','Rainbow Six':'Rainbow Six','Valorant':'VALORANT'}
def nid(fid,st): return "m"+st[:10].replace('-','')+"-"+hashlib.sha1(fid.encode()).hexdigest()[:8]
out=[];skipped=[]
for e in b['events']:
    fid='bov:'+str(e['id'])
    if e['sport']=='tennis': skipped.append((fid,'テニスはtennisexplorer（ブック別）を使用')); continue
    if 'Series' in e['league']: skipped.append((fid,'シリーズ勝者市場（単一試合でない）')); continue
    if e['start_jst']<=LOCK or core.parse(e['start_jst']).timestamp()>H24: continue
    if e.get('live'): continue
    sp = ES.get(e['league'].split(' / ')[0],'eスポーツ（その他）') if e['sport']=='esports' else SP.get(e['sport'],e['sport'])
    mk=e.get('market'); prices=None
    if mk:
        oc=mk['outcomes']; two=[o for o in oc if (o.get('type') or '')!='D' and (o.get('name') or '').lower()!='draw']
        if len(two)==2:
            prices={'L':round(two[0]['dec'],3),'R':round(two[1]['dec'],3)}
            d=[o for o in oc if o not in two]
            if d: prices['D']=round(d[0]['dec'],3)
        left,right=two[0]['name'],two[1]['name'] if len(two)==2 else (None,None)
    if not mk or not prices:
        tm=[x['name'] for x in e.get('teams') or []]
        parts=re.split(r'\s+(?:vs\.?|@|v)\s+',e['desc'] or '')
        left,right=(parts+[None,None])[:2] if len(parts)>=2 else (tm+[None,None])[:2]
    out.append(dict(fid=fid,sport=sp,league=e['league'],start_jst=e['start_jst'],left=left,right=right,desc=e['desc'],
        at=' @ ' in (e['desc'] or ''),prices=prices,book='Bovada',src='Bovada',taken_at=b['taken_at'],market=(mk or {}).get('market') or 'Moneyline',
        new_id=nid(fid,e['start_jst']),books=None))
for e in t['matches']:
    fid='te:'+str(e['id'])
    if e['start_jst']<=LOCK or core.parse(e['start_jst']).timestamp()>H24: continue
    pk=e.get('pick')
    out.append(dict(fid=fid,sport='テニス',league=e['tournament'],start_jst=e['start_jst'],left=e['p1'],right=e['p2'],desc=None,at=False,
        prices={'L':pk['L'],'R':pk['R']} if pk else None,book=pk['book'] if pk else None,src='tennisexplorer',taken_at=t['taken_at'],
        market='Match Winner（2way）',new_id=nid(fid,e['start_jst']),books=e.get('books'),names_full=e.get('names_full')))
json.dump(out,open('/home/claude/dd/feed_inv.json','w'),ensure_ascii=False,indent=0)
json.dump(skipped,open('/home/claude/dd/feed_skipped.json','w'),ensure_ascii=False)
import collections
print(len(out),collections.Counter(x['sport'] for x in out),sum(1 for x in out if x['prices']))
