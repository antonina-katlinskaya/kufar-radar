import json
from .matcher import apply_mismatch_policy, match_new
from .store import fp, now, current_bir, inactive_bir
from .collectors.kufar import is_mw_claimed
from .config import settings

class AuditSession:
    def __init__(self, db):
        self.db=db
        self.candidates=current_bir(db)
        self.inactive_candidates=inactive_bir(db)
        self.active={}
        for r in db.query('SELECT * FROM events WHERE active=1 AND occurred_at >= ?',[settings.live_cutoff_utc]):
            self.active.setdefault(r['ad_id'],{})[r['field_name']]=r
        self.statements=[]

    def audit(self,k):
        r=match_new(k,self.candidates)

        if r.obj:
            mismatches=apply_mismatch_policy(k,r.obj,r.mismatches)
            if r.confidence in {'EXACT','HIGH'}:
                ts=now()
                self.statements.append((
                  'INSERT INTO matches(ad_id,object_key,confidence,reason,updated_at) VALUES(?,?,?,?,?) '
                  'ON CONFLICT(ad_id) DO UPDATE SET object_key=excluded.object_key,confidence=excluded.confidence,'
                  'reason=excluded.reason,updated_at=excluded.updated_at',
                  [k.ad_id,r.obj.object_key,r.confidence,r.reason,ts]
                ))
            return {
              'status':'MISMATCH' if mismatches else 'OK',
              'ad_id':k.ad_id,
              'object_key':r.obj.object_key,
              'confidence':r.confidence,
              'reason':r.reason,
              'mismatches':mismatches
            }

        if not is_mw_claimed(k):
            return {'status':'OUT_OF_SCOPE','ad_id':k.ad_id,'reason':'No Minsk World marker and no Bir match','mismatches':{}}

        if r.confidence=='AMBIGUOUS':
            return {'status':'AMBIGUOUS','ad_id':k.ad_id,'reason':r.reason,'mismatches':{}}

        historical=match_new(k,self.inactive_candidates)
        if historical.confidence=='AMBIGUOUS':
            return {'status':'AMBIGUOUS','ad_id':k.ad_id,'reason':'Historical Bir match is ambiguous','mismatches':{}}

        known=sum(v is not None and v!='' for v in [k.price_eur,k.area,k.rooms,k.floor,k.address])
        if known>=4 and historical.obj and historical.confidence in {'EXACT','HIGH'}:
            return {
              'status':'NO_BIR_OBJECT',
              'ad_id':k.ad_id,
              'object_key':historical.obj.object_key,
              'reason':historical.reason,
              'mismatches':{'existence':('active Kufar','no matching current Bir object')}
            }

        return {'status':'INSUFFICIENT','ad_id':k.ad_id,'reason':'No confident current or historical Bir match','mismatches':{}}

    def sync(self,k,result):
        ts=now(); status=result.get('status'); mism=result.get('mismatches') or {}; desired={}

        if status=='NO_BIR_OBJECT':
            desired['existence']=('active Kufar','no matching current Bir object','NO_BIR_OBJECT')
        elif status=='MISMATCH':
            for field,(a,b) in mism.items():
                desired[field]=(str(a),json.dumps(b,ensure_ascii=False) if isinstance(b,(dict,list)) else str(b),'NEW_MISMATCH')

        active=self.active.get(k.ad_id,{})
        new_events=[]

        for field,e in list(active.items()):
            if field not in desired:
                self.statements.append(('UPDATE events SET active=0,resolved_at=? WHERE id=?',[ts,e['id']]))
                del active[field]

        for field,(nv,bv,typ) in desired.items():
            sig=fp([k.ad_id,field,nv,bv]); cur=active.get(field)
            if cur and cur.get('signature')==sig:
                continue
            if cur and cur.get('id') is not None:
                self.statements.append(('UPDATE events SET active=0,resolved_at=? WHERE id=?',[ts,cur['id']]))

            self.statements.append((
              'INSERT INTO events(ad_id,object_key,event_type,field_name,old_value,new_value,bir_value,active,occurred_at,signature) '
              'VALUES(?,?,?,?,?,?,?,?,?,?)',
              [k.ad_id,result.get('object_key'),typ,field,cur.get('new_value') if cur else None,nv,bv,1,ts,sig]
            ))
            active[field]={
              'id':None,'ad_id':k.ad_id,'object_key':result.get('object_key'),
              'event_type':typ,'field_name':field,'new_value':nv,'bir_value':bv,
              'signature':sig,'active':1,'occurred_at':ts
            }
            new_events.append({
              'event_type':typ,'field_name':field,'ad_id':k.ad_id,
              'old_value':cur.get('new_value') if cur else None,
              'new_value':nv,'bir_value':bv,'object_key':result.get('object_key'),
              'occurred_at':ts
            })

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

def audit_one(db,k):
    s=AuditSession(db); r=s.audit(k); s.flush(); return r

def sync_events(db,k,result):
    s=AuditSession(db); out=s.sync(k,result); s.flush(); return out
