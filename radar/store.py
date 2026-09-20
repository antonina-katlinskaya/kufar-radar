import json, hashlib
from datetime import datetime, timezone
from .models import KufarListing, BirListing

def now(): return datetime.now(timezone.utc).isoformat()
def fp(v): return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def load_current_kufar(db,profile_id):
    return {r['ad_id']:r for r in db.query('SELECT * FROM kufar_ads WHERE profile_id=?',[profile_id])}

def save_kufar(db,items,profile_id):
    cur=load_current_kufar(db,profile_id); ts=now(); changed=[]; seen=set(); stm=[]
    prev_active=sum(1 for r in cur.values() if r.get('active'))
    if prev_active>=50 and len(items)<int(prev_active*0.70):
        raise RuntimeError(f'Invalid Kufar snapshot: got {len(items)}, previous active {prev_active}')

    for x in items:
        seen.add(x.ad_id)
        f=fp([x.price_eur,x.price_byn,x.area,x.rooms,x.floor,x.address])
        old=cur.get(x.ad_id)
        is_changed=(not old or old.get('fingerprint')!=f or not old.get('active'))
        if not is_changed:
            continue

        changed.append(x)
        stm.append(("""INSERT INTO kufar_ads(ad_id,profile_id,url,active,first_seen_at,last_seen_at,price_eur,price_byn,area,rooms,floor,address,title,fingerprint,raw_json)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(ad_id) DO UPDATE SET url=excluded.url,active=1,last_seen_at=excluded.last_seen_at,price_eur=excluded.price_eur,price_byn=excluded.price_byn,area=excluded.area,rooms=excluded.rooms,floor=excluded.floor,address=excluded.address,title=excluded.title,fingerprint=excluded.fingerprint,raw_json=excluded.raw_json""",
          [x.ad_id,profile_id,x.url,1,(old or {}).get('first_seen_at',ts),ts,x.price_eur,x.price_byn,x.area,x.rooms,x.floor,x.address,x.title,f,json.dumps(x.raw,ensure_ascii=False)]))
        stm.append(('INSERT INTO kufar_versions(ad_id,observed_at,price_eur,price_byn,area,rooms,floor,address,title,fingerprint,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
          [x.ad_id,ts,x.price_eur,x.price_byn,x.area,x.rooms,x.floor,x.address,x.title,f,json.dumps(x.raw,ensure_ascii=False)]))

    for aid,old in cur.items():
        if old.get('active') and aid not in seen:
            stm.append(('UPDATE kufar_ads SET active=0,last_seen_at=? WHERE ad_id=?',[ts,aid]))

    for i in range(0,len(stm),75): db.batch(stm[i:i+75])
    return changed

def save_bir(db,items):
    cur={r['object_key']:r for r in db.query('SELECT * FROM bir_objects')}; ts=now(); seen=set(); stm=[]
    prev_active=sum(1 for r in cur.values() if r.get('active'))
    if len(items)<20 or (prev_active>=50 and len(items)<int(prev_active*0.70)):
        raise RuntimeError(f'Invalid Bir snapshot: got {len(items)}, previous active {prev_active}')

    for x in items:
        seen.add(x.object_key); old=cur.get(x.object_key)
        data_changed=(not old or any(old.get(k)!=v for k,v in [
            ('building_name',x.building_name),
            ('price_regular_eur',x.price_regular_eur),
            ('price_fast_eur',x.price_fast_eur),
            ('area',x.area),
            ('rooms',x.rooms),
            ('floor',x.floor),
            ('official_address',x.official_address)
        ]))
        reappeared=bool(old and not old.get('active'))
        if not data_changed and not reappeared:
            continue

        stm.append(("""INSERT INTO bir_objects(object_key,building_name,official_address,unit_no,active,first_seen_at,last_seen_at,price_regular_eur,price_fast_eur,area,rooms,floor,raw_json)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(object_key) DO UPDATE SET building_name=excluded.building_name,official_address=excluded.official_address,unit_no=excluded.unit_no,active=1,last_seen_at=excluded.last_seen_at,price_regular_eur=excluded.price_regular_eur,price_fast_eur=excluded.price_fast_eur,area=excluded.area,rooms=COALESCE(excluded.rooms,bir_objects.rooms),floor=excluded.floor,raw_json=excluded.raw_json""",
          [x.object_key,x.building_name,x.official_address,x.unit_no,1,(old or {}).get('first_seen_at',ts),ts,x.price_regular_eur,x.price_fast_eur,x.area,x.rooms,x.floor,json.dumps(x.raw,ensure_ascii=False)]))
        if data_changed:
            stm.append(('INSERT INTO bir_versions(object_key,observed_at,price_regular_eur,price_fast_eur,area,rooms,floor,official_address,raw_json) VALUES(?,?,?,?,?,?,?,?,?)',
              [x.object_key,ts,x.price_regular_eur,x.price_fast_eur,x.area,x.rooms,x.floor,x.official_address,json.dumps(x.raw,ensure_ascii=False)]))

    previous_good=db.get_state('last_bir_success') or ts
    for key,old in cur.items():
        if old.get('active') and key not in seen:
            stm.append(('UPDATE bir_objects SET active=0,last_seen_at=? WHERE object_key=?',[previous_good,key]))

    for i in range(0,len(stm),75): db.batch(stm[i:i+75])

def current_bir(db):
    out=[]
    for r in db.query('SELECT * FROM bir_objects WHERE active=1'):
        raw={}
        try: raw=json.loads(r.get('raw_json') or '{}')
        except: pass
        out.append(BirListing(r['object_key'],r.get('building_name'),r.get('official_address'),r.get('unit_no'),r.get('price_regular_eur'),r.get('price_fast_eur'),r.get('area'),r.get('rooms'),r.get('floor'),raw))
    return out

def current_kufar(db,profile_id):
    out=[]
    for r in db.query('SELECT * FROM kufar_ads WHERE active=1 AND profile_id=?',[profile_id]):
        raw={}
        try: raw=json.loads(r.get('raw_json') or '{}')
        except: pass
        out.append(KufarListing(r['ad_id'],r.get('url') or '',profile_id,r.get('price_eur'),r.get('price_byn'),r.get('area'),r.get('rooms'),r.get('floor'),r.get('address'),r.get('title'),raw))
    return out


def inactive_bir(db):
    out=[]
    for r in db.query('SELECT * FROM bir_objects WHERE active=0'):
        raw={}
        try: raw=json.loads(r.get('raw_json') or '{}')
        except: pass
        out.append(BirListing(r['object_key'],r.get('building_name'),r.get('official_address'),r.get('unit_no'),r.get('price_regular_eur'),r.get('price_fast_eur'),r.get('area'),r.get('rooms'),r.get('floor'),raw))
    return out
