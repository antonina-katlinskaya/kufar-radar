import json
from .matcher import match_new, mismatch_map, MatchResult
from .store import fp, now, current_bir

def audit_one(db,k):
    candidates=current_bir(db)
    rows=db.query('SELECT * FROM matches WHERE ad_id=? LIMIT 1',[k.ad_id])
    if rows:
        m=rows[0]; b=next((x for x in candidates if x.object_key==m['object_key']),None)
        if not b: return {'status':'STALE','ad_id':k.ad_id,'object_key':m['object_key'],'mismatches':{'existence':('active Kufar','previously matched Bir object missing')}}
        r=MatchResult(b,m['confidence'],'Historical binding',mismatch_map(k,b))
    else:
        r=match_new(k,candidates)
        if r.obj and r.confidence in {'EXACT','HIGH'}:
            db.execute('INSERT INTO matches(ad_id,object_key,confidence,reason,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(ad_id) DO UPDATE SET object_key=excluded.object_key,confidence=excluded.confidence,reason=excluded.reason,updated_at=excluded.updated_at',[k.ad_id,r.obj.object_key,r.confidence,r.reason,now()])
    if not r.obj: return {'status':r.confidence,'ad_id':k.ad_id,'reason':r.reason,'mismatches':{}}
    return {'status':'MISMATCH' if r.mismatches else 'OK','ad_id':k.ad_id,'object_key':r.obj.object_key,'confidence':r.confidence,'reason':r.reason,'mismatches':r.mismatches}

def sync_events(db,k,result):
    ts=now(); status=result.get('status'); mism=result.get('mismatches') or {}; desired={}
    st=db.query('SELECT * FROM unmatched_state WHERE ad_id=?',[k.ad_id]); st=st[0] if st else None
    if status=='NONE':
        count=(st.get('consecutive_count',0)+1) if st else 1
        db.execute('INSERT INTO unmatched_state(ad_id,consecutive_count,first_seen_at,last_seen_at) VALUES(?,?,?,?) ON CONFLICT(ad_id) DO UPDATE SET consecutive_count=?,last_seen_at=?',[k.ad_id,count,(st or {}).get('first_seen_at',ts),ts,count,ts])
        if count>=2: desired['existence']=('active Kufar','no matching current Bir object','NO_BIR_OBJECT')
    elif status=='STALE':
        desired['existence']=('active Kufar','previously matched Bir object missing','STALE')
        if st: db.execute('UPDATE unmatched_state SET consecutive_count=0,last_seen_at=? WHERE ad_id=?',[ts,k.ad_id])
    else:
        if st: db.execute('UPDATE unmatched_state SET consecutive_count=0,last_seen_at=? WHERE ad_id=?',[ts,k.ad_id])
        if status=='MISMATCH':
            for field,(a,b) in mism.items(): desired[field]=(str(a),json.dumps(b,ensure_ascii=False) if isinstance(b,(dict,list)) else str(b),'MISMATCH')
    active={r['field_name']:r for r in db.query('SELECT * FROM events WHERE ad_id=? AND active=1',[k.ad_id])}
    new_events=[]
    for field,e in active.items():
        if field not in desired:
            db.execute('UPDATE events SET active=0,resolved_at=? WHERE id=?',[ts,e['id']])
            sig=fp([k.ad_id,'RESTORED',field,ts])
            db.execute('INSERT INTO events(ad_id,object_key,event_type,field_name,old_value,new_value,bir_value,active,occurred_at,signature) VALUES(?,?,?,?,?,?,?,?,?,?)',[k.ad_id,e.get('object_key'),'RESTORED',field,e.get('new_value'),'restored',e.get('bir_value'),0,ts,sig])
            new_events.append({'event_type':'RESTORED','field_name':field,'ad_id':k.ad_id,'old_value':e.get('new_value'),'new_value':'restored','bir_value':e.get('bir_value')})
    for field,(nv,bv,base) in desired.items():
        sig=fp([k.ad_id,field,nv,bv]); cur=active.get(field)
        if cur and cur.get('signature')==sig: continue
        if cur: db.execute('UPDATE events SET active=0,resolved_at=? WHERE id=?',[ts,cur['id']])
        prior=db.query('SELECT id FROM events WHERE ad_id=? AND field_name=? AND new_value=? AND active=0 LIMIT 1',[k.ad_id,field,nv])
        typ=base if base in {'STALE','NO_BIR_OBJECT'} else ('REPEAT' if prior else 'NEW_MISMATCH')
        db.execute('INSERT INTO events(ad_id,object_key,event_type,field_name,old_value,new_value,bir_value,active,occurred_at,signature) VALUES(?,?,?,?,?,?,?,?,?,?)',[k.ad_id,result.get('object_key'),typ,field,cur.get('new_value') if cur else None,nv,bv,1,ts,sig])
        new_events.append({'event_type':typ,'field_name':field,'ad_id':k.ad_id,'old_value':cur.get('new_value') if cur else None,'new_value':nv,'bir_value':bv})
    return new_events
