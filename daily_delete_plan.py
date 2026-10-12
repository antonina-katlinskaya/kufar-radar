"""Generate ONE frozen daily Kufar removal plan from fresh radar D1 data.
Does not log into Kufar or delete any ads. Requires existing CF_* environment secrets.
"""
import csv, json, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from radar.d1 import D1

PROFILE='11093294'
TARGET=1000
PER_HOUR=6
HOURS=list(range(7,24))
CAP=PER_HOUR*len(HOURS)
MIN_KEEP_DEFAULT=2
MIN_KEEP_SMALL=4
MIN_AGE_HOURS=24
SQL="""
SELECT ad_id, profile_id, area, list_time, price_eur, url
FROM kufar_ads_live
WHERE profile_id=? AND present=1
ORDER BY area, list_time, ad_id
"""
def plan(rows, snapshot_at, expected_publications=95, day=None):
    now=datetime.now(timezone.utc)
    if not rows: raise ValueError('Radar returned zero active ads; stop')
    if not snapshot_at or now-snapshot_at>timedelta(minutes=45):
        raise ValueError('Radar active-ad snapshot is stale; stop')
    date=day or now.astimezone(ZoneInfo('Europe/Minsk')).date()
    groups={}
    all_ids=set()
    for r in rows:
        if r['profile_id']!=PROFILE: raise ValueError('Wrong profile; stop')
        key=str(r.get('ad_id') or '')
        if not key or key in all_ids: raise ValueError('Missing/duplicate ad ID; stop')
        all_ids.add(key)
        area=r.get('area')
        if area is None or float(area)<=0: raise ValueError('Missing area; stop')
        if not r.get('list_time') or not r.get('url'): raise ValueError('Missing date or URL; stop')
        groups.setdefault(float(area),[]).append(r)
    limit=min(CAP,max(0,len(rows)+expected_publications-TARGET))
    available=[]
    for area,items in groups.items():
        items.sort(key=lambda r:(r['list_time'],str(r['ad_id'])))
        keep=MIN_KEEP_SMALL if area<30 else MIN_KEEP_DEFAULT
        surplus=max(0,len(items)-keep)
        for ad in items[:surplus]:
            stamp=datetime.fromisoformat(str(ad['list_time']).replace('Z','+00:00'))
            if stamp.tzinfo is None: stamp=stamp.replace(tzinfo=timezone.utc)
            if now-stamp<timedelta(hours=MIN_AGE_HOURS): continue
            available.append((len(items),stamp,ad,area,keep))
    available.sort(key=lambda x:(-x[0],x[1],str(x[2]['ad_id'])))
    selected=[]
    by_area={}
    for group_count,stamp,ad,area,keep in available:
        if len(selected)>=limit:break
        if len(groups[area])-by_area.get(area,0)<=keep:continue
        by_area[area]=by_area.get(area,0)+1
        selected.append((ad,area,group_count,keep))
    out=[]
    for i,(ad,area,group_count,keep) in enumerate(selected):
        hour=HOURS[i//PER_HOUR]; minute=5+(i%PER_HOUR)*9
        out.append({'date':date.strftime('%d.%m.%Y'),'time':f'{hour:02d}:{minute:02d}',
                    'profile_id':PROFILE,'ad_id':str(ad['ad_id']),'url':ad['url'],
                    'area':area,'price_eur':ad.get('price_eur'),'published_at':ad['list_time'],
                    'group_count':group_count,'reason':f'Oldest surplus; retain {keep} of area {area}',
                    'status':'PLANNED','result':'','checked_at':''})
    return {'date':str(date),'profile_id':PROFILE,'source':'radar_D1_kufar_ads_live',
            'snapshot_at':snapshot_at.isoformat(),'active_count':len(rows),
            'expected_publications':expected_publications,'target':TARGET,
            'planned_count':len(out),'max_per_hour':PER_HOUR,'rows':out}
def main():
    d1=D1()
    meta=d1.query('SELECT last_cycle_at AS seen FROM kufar_bridge_state WHERE profile_id=? LIMIT 1',[PROFILE])
    stamp=(meta[0] or {}).get('seen') if meta else None
    snap=datetime.fromisoformat(str(stamp).replace('Z','+00:00')) if stamp else None
    if snap and snap.tzinfo is None:snap=snap.replace(tzinfo=timezone.utc)
    rows=d1.query(SQL,[PROFILE])
    expected=int(os.getenv('EXPECTED_PUBLICATIONS','95'))
    report=plan(rows,snap,expected)
    folder=Path(__file__).parent/'exports'/'daily-delete'
    folder.mkdir(parents=True,exist_ok=True)
    stem=f"DELETE_PLAN_{report['date'].replace('.','-')}"
    (folder/(stem+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (folder/(stem+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['date','time','profile_id','ad_id','url','area','price_eur','published_at','group_count','reason','status','result','checked_at'])
        writer.writeheader();writer.writerows(report['rows'])
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False))
if __name__=='__main__':
    main()
