"""Daily Kufar removal CANDIDATES; no deletion operations. Residential only, fail closed."""
import csv, json, os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from radar.d1 import D1

PROFILE='11093294'
PER_HOUR=6
HOURS=list(range(7,24))
CAP=PER_HOUR*len(HOURS)
KEEP_PER_DAY=15
TZ=ZoneInfo('Europe/Minsk')
SQL="""SELECT ad_id, profile_id, area, list_time, price_eur, price_byn, url, raw_json
FROM kufar_ads_live WHERE profile_id=? AND present=1
ORDER BY ad_id"""

def parse_dt(s):
    v=datetime.fromisoformat(str(s).replace('Z','+00:00'))
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v

def type_of(ad):
    """Only explicit category evidence can mark residential; unknown is always protected."""
    try: raw=json.loads(ad.get('raw_json') or '{}')
    except (TypeError, ValueError): return 'UNKNOWN'
    if not isinstance(raw,dict):return 'UNKNOWN'
    # Kufar raw data may differ by category and collection generation.
    # Never infer 'residential' from price, area, rooms, URL, or a textual title.
    # Require a verified category field AND approved category mapping.
    identifier=str(raw.get('category') or '')
    params=raw.get('ad_parameters') or []
    category_param=next((x for x in params if isinstance(x,dict) and x.get('p')=='category'),None)
    # Verified against the live 12 Oct 2026 radar D1 snapshot: 1010 = Квартиры.
    if identifier=='1010' and category_param and str(category_param.get('v'))=='1010' and category_param.get('vl')=='Квартиры':
        return 'RESIDENTIAL'
    return 'PROTECTED_UNKNOWN_OR_COMMERCIAL'

def plan(rows,snapshot_at,expected_publications=0,day=None):
    now=datetime.now(timezone.utc)
    if not snapshot_at or now-snapshot_at>timedelta(hours=3):raise ValueError('Radar completed scan not fresh; abort')
    if not rows:raise ValueError('No active ads; abort')
    ids=set()
    grouped=defaultdict(list)
    protected=0
    for ad in rows:
        id=str(ad.get('ad_id') or '')
        if ad.get('profile_id')!=PROFILE or not id or id in ids:raise ValueError('Profile/ID mismatch')
        ids.add(id)
        if type_of(ad)!='RESIDENTIAL':
            protected+=1
            continue
        if ad.get('price_byn') is None or not ad.get('list_time') or not ad.get('url'):
            protected+=1
            continue
        published=parse_dt(ad['list_time'])
        if published>now+timedelta(minutes=5):raise ValueError('Future publication timestamp')
        date=published.astimezone(TZ).date()
        grouped[date].append((float(ad['price_byn']),published,id,ad))
    surplus=[]
    for date,items in sorted(grouped.items()):
        # Cheapest first, and for a price tie preserve the LATEST listings.
        sorted_items=sorted(items,key=lambda x:(x[0],-x[1].timestamp(),x[2]))
        for cost,published,id,ad in sorted_items[KEEP_PER_DAY:]:
            surplus.append((date,published,id,ad,len(items)))
    # Earliest days first, earliest posts first among deletable surplus.
    surplus.sort(key=lambda x:(x[0],x[1],x[2]))
    day=day or now.astimezone(TZ).date()
    chosen=surplus[:CAP]
    output=[]
    for i,(published_day,published,id,ad,n) in enumerate(chosen):
        h=HOURS[i//PER_HOUR]; minute=5+9*(i%PER_HOUR)
        output.append({
            'date':day.strftime('%d.%m.%Y'),'time':f'{h:02d}:{minute:02d}',
            'profile_id':PROFILE,'ad_id':id,'url':ad['url'],'area':ad.get('area'),
            'price_eur':ad.get('price_eur'),'published_at':ad['list_time'],
            'group_count':n,'reason':f'Residential surplus on {published_day}; keep 15 cheapest, latest on ties',
            'status':'REVIEW_REQUIRED','result':'','checked_at':''})
    return {'date':str(day),'profile_id':PROFILE,'source':'radar_D1_kufar_ads_live',
            'snapshot_at':snapshot_at.isoformat(),'active_count':len(rows),
            'protected_unclassified_count':protected,'residential_days_verified':len(grouped),
            'eligible_count':len(surplus),'planned_count':len(output),
            'max_per_hour':PER_HOUR,'execution_enabled':False,'rows':output}

def main():
    raise RuntimeError('DISABLED: profile 11093294 is Alyona Dovgun, not Elena Boriskina. Use verified employee profile 11852045 only.')
    db=D1()
    meta=db.query('SELECT last_cycle_at AS seen FROM kufar_bridge_state WHERE profile_id=? LIMIT 1',[PROFILE])
    stamp=(meta[0] or {}).get('seen') if meta else None
    snapshot=parse_dt(stamp) if stamp else None
    total=int(db.query('SELECT COUNT(*) AS total FROM kufar_ads_live WHERE profile_id=? AND present=1',[PROFILE])[0]['total'])
    rows=[]
    for offset in range(0,total,400):
        page=db.query(SQL+' LIMIT ? OFFSET ?',[PROFILE,400,offset])
        rows.extend(page)
    if len(rows)!=total:raise ValueError(f'Incomplete inventory {len(rows)}/{total}')
    report=plan(rows,snapshot)
    out=Path(__file__).parent/'exports'/'daily-delete'
    out.mkdir(parents=True,exist_ok=True)
    stem='DELETE_PLAN_'+report['date']
    (out/(stem+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    cols=['date','time','profile_id','ad_id','url','area','price_eur','published_at','group_count','reason','status','result','checked_at']
    with (out/(stem+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader();writer.writerows(report['rows'])
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False))
if __name__=='__main__':main()
