import json,sys,re
sys.path.insert(0,'/home/claude/rmc-board')
from rmc import core
from rmc.oddsfeed import _n as _n0
STOP={'u19','u21','u20','u23','u17','town','city','united','utd','de','les','women','sc','ac','cf','fk','jk','sk','hc','bk','if','real','sporting','athletic','ii','reserves','the','and','of','la','le','del','st'}
def _n(s): return _n0(s)-STOP
m=core.load('matches.json'); feed=json.load(open('/home/claude/dd/feed_inv.json'))
byfid={}
for mid,x in m.items():
    for f in x.get('feed_ids',[]): byfid[f]=mid
out=[];nm=0
for x in feed:
    if x['fid'] in byfid:
        mid=byfid[x['fid']]; mm=m[mid]
        sw = bool(_n(mm['left'])&_n(x['right']) and not _n(mm['left'])&_n(x['left']))
        out.append(dict(fid=x['fid'],match_id=mid,swapped=sw,how='feed_id'));continue
    t0=core.parse(x['start_jst']).timestamp()
    for mid,mm in m.items():
        if mm['status'] not in('scheduled','unknown') or mm['sport']!=x['sport'] or abs(core.parse(mm['start_jst']).timestamp()-t0)>3*3600: continue
        L,R=_n(mm['left']),_n(mm['right']);a,b=_n(x['left']),_n(x['right'])
        if L&a and R&b: out.append(dict(fid=x['fid'],match_id=mid,swapped=False,how='name'));nm+=1;break
        if L&b and R&a: out.append(dict(fid=x['fid'],match_id=mid,swapped=True,how='name'));nm+=1;break
json.dump(out,open('/home/claude/dd/mapping.json','w'),ensure_ascii=False,indent=0)
print(len(out),'mapped; by name',nm)
for o in out:
    if o['how']=='name' or o['swapped']: print(o, m[o['match_id']]['left'],'vs',m[o['match_id']]['right'])
