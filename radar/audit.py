import json
from .matcher import match_new, mismatch_map, MatchResult
from .store import fp, now, current_bir
from .collectors.kufar import is_mw_claimed

class AuditSession:
    def __init__(self, db):
        self.db=db
        self.candidates=current_bir(db)
        self.bir_by_key={x.object_key:x for x in self.candidates}
        self.matches={r['ad_id']:r for r in db.query('SELECT * FROM matches')}
        self.unmatched={r['ad_id']:r for r in db.query('SELECT * FROM unmatched_state')}
        self.active={}
        for r in db.query('SELECT * FROM events WHERE active=1'):
            self.active.setdefault(r['ad_id'],{})[r['field_name']]=r
        self.prior={(r['ad_id'],r['field_name'],r.get('new_value')) for r in db.query('SELECT ad_id,field_name,new_value FROM events WHERE active=0')}
        self.statements=[]

    def audit(self,k):
        m=self.matches.get(k.ad_id)
        if m:
            b=self.bir_by_key.get(m['object_key'])
            if not b:
                return {'status':'STALE','ad_id':k.ad_id,'object_key':m['object_key'],'mismatches':{'existence':('active Kufar','previously matched Bir object missing')}}
            r=MatchResult(b,m['confidence'],'Historical binding',mismatch_map(k,b))
        else:
            r=match_new(k,self.candidates)
            if r.obj and r.confidence in {'EXACT','HIGH'}:
                ts=now()
                self.statements.append((
                  'INSERT INTO matches(ad_id,object_key,confidence,reason,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(ad_id) DO UPDATE SET object_key=excluded.object_key,confidence=excluded.confidence,reason=excluded.reason,updated_at=excluded.updated_at',
                  [k.ad_id,r.obj.object_key,r.confidence,r.reason,ts]
                ))
                self.matches[k.ad_id]={'ad_id':k.ad_id,'object_key':r.obj.object_key,'confidence':r.confidence,'reason':r.reason,'updated_at':ts}
        if not r.obj:
            if not is_mw_claimed(k):
                return {'status':'OUT_OF_SCOPE','ad_id':k.ad_id,'reason':'No Minsk World marker and no Bir match','mismatches':{}}
            return {'status':r.confidence,'ad_id':k.ad_id,'reason':r.reason,'mismatches':{}}
        return {'status':'MISMATCH' if r.mismatches else 'OK','ad_id':k.ad_id,'object_key':r.obj.object_key,'confidence':r.confidence,'reason':r.reason,'mismatches':r.mismatches}

    def sync(self,k,result):
        ts=now(); status=result.get('status'); mism=result.get('mismatches') or {}; desired={}
        st=self.unmatched.get(k.ad_id)

        if status=='NONE':
            count=(int(st.get('consecutive_count') or 0)+1) if st else 1
            first=(st or {}).get('first_seen_at') or ts
            self.statements.append((
              'INSERT INTO unmatched_state(ad_id,consecutive_count,first_seen_at,last_seen_at) VALUES(?,?,?,?) ON CONFLICT(ad_id) DO UPDATE SET consecutive_count=excluded.consecutive_count,last_seen_at=excluded.last_seen_at',
              [k.ad_id,count,first,ts]
            ))
            self.unmatched[k.ad_id]={'ad_id':k.ad_id,'consecutive_count':count,'first_seen_at':first,'last_seen_at':ts}
            if count>=2:
                desired['existence']=('active Kufar','no matching current Bir object','NO_BIR_OBJECT')
        elif status=='STALE':
            desired['existence']=('active Kufar','previously matched Bir object missing','STALE')
            if st and int(st.get('consecutive_count') or 0)!=0:
                self.statements.append(('UPDATE unmatched_state SET consecutive_count=0,last_seen_at=? WHERE ad_id=?',[ts,k.ad_id]))
                st['consecutive_count']=0; st['last_seen_at']=ts
        else:
            if st and int(st.get('consecutive_count') or 0)!=0:
                self.statements.append(('UPDATE unmatched_state SET consecutive_count=0,last_seen_at=? WHERE ad_id=?',[ts,k.ad_id]))
                st['consecutive_count']=0; st['last_seen_at']=ts
            if status=='MISMATCH':
                for field,(a,b) in mism.items():
                    desired[field]=(str(a),json.dumps(b,ensure_ascii=False) if isinstance(b,(dict,list)) else str(b),'MISMATCH')

        active=self.active.get(k.ad_id,{})
        new_events=[]

        for field,e in list(active.items()):
            if field not in desired:
                self.statements.append(('UPDATE events SET active=0,resolved_at=? WHERE id=?',[ts,e['id']]))
                sig=fp([k.ad_id,'RESTORED',field,ts])
                self.statements.append((
                  'INSERT INTO events(ad_id,object_key,event_type,field_name,old_value,new_value,bir_value,active,occurred_at,signature) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  [k.ad_id,e.get('object_key'),'RESTORED',field,e.get('new_value'),'restored',e.get('bir_value'),0,ts,sig]
                ))
                self.prior.add((k.ad_id,field,e.get('new_value')))
                del active[field]
                new_events.append({'event_type':'RESTORED','field_name':field,'ad_id':k.ad_id,'old_value':e.get('new_value'),'new_value':'restored','bir_value':e.get('bir_value')})

        for field,(nv,bv,base) in desired.items():
            sig=fp([k.ad_id,field,nv,bv]); cur=active.get(field)
            if cur and cur.get('signature')==sig:
                continue
            if cur and cur.get('id') is not None:
                self.statements.append(('UPDATE events SET active=0,resolved_at=? WHERE id=?',[ts,cur['id']]))
                self.prior.add((k.ad_id,field,cur.get('new_value')))
            repeated=(k.ad_id,field,nv) in self.prior
            typ=base if base in {'STALE','NO_BIR_OBJECT'} else ('REPEAT' if repeated else 'NEW_MISMATCH')
            self.statements.append((
              'INSERT INTO events(ad_id,object_key,event_type,field_name,old_value,new_value,bir_value,active,occurred_at,signature) VALUES(?,?,?,?,?,?,?,?,?,?)',
              [k.ad_id,result.get('object_key'),typ,field,cur.get('new_value') if cur else None,nv,bv,1,ts,sig]
            ))
            active[field]={'id':None,'ad_id':k.ad_id,'object_key':result.get('object_key'),'event_type':typ,'field_name':field,'new_value':nv,'bir_value':bv,'signature':sig,'active':1}
            new_events.append({'event_type':typ,'field_name':field,'ad_id':k.ad_id,'old_value':cur.get('new_value') if cur else None,'new_value':nv,'bir_value':bv})

        if active:
            self.active[k.ad_id]=active
        elif k.ad_id in self.active:
            del self.active[k.ad_id]
        return new_events

    def flush(self):
        for i in range(0,len(self.statements),75):
            self.db.batch(self.statements[i:i+75])
        n=len(self.statements)
        self.statements.clear()
        return n

# Compatibility wrappers for tests/older code.
def audit_one(db,k):
    s=AuditSession(db); r=s.audit(k); s.flush(); return r

def sync_events(db,k,result):
    s=AuditSession(db); out=s.sync(k,result); s.flush(); return out
