import json
from .matcher import apply_mismatch_policy, match_for_audit_field, match_new, vector
from .house_directory import resolved_bir_address
from .store import fp, now, current_bir, inactive_bir
from .collectors.kufar import is_mw_claimed
from .config import settings

class AuditSession:
    def __init__(self, db, ad_ids=None):
        self.db=db
        self.candidates=current_bir(db)
        self.inactive_candidates=inactive_bir(db)
        self.active={}
        for r in db.query('SELECT * FROM events WHERE active=1 AND occurred_at >= ?',[settings.live_cutoff_utc]):
            self.active.setdefault(r['ad_id'],{})[r['field_name']]=r
        self.preferred={}
        wanted=list(dict.fromkeys(str(ad_id) for ad_id in (ad_ids or [])))
        if wanted:
            for i in range(0,len(wanted),75):
                chunk=wanted[i:i+75]
                marks=','.join('?' for _ in chunk)
                for r in db.query(
                  f'SELECT ad_id,object_key FROM matches WHERE ad_id IN ({marks})',chunk
                ):
                    if r.get('ad_id') is not None and r.get('object_key') is not None:
                        self.preferred[str(r['ad_id'])]=str(r['object_key'])
        self.statements=[]

    def remember_match(self,k,obj,confidence,reason):
        if not obj:
            return
        ts=now()
        self.statements.append((
          'INSERT INTO matches(ad_id,object_key,confidence,reason,updated_at) VALUES(?,?,?,?,?) '
          'ON CONFLICT(ad_id) DO UPDATE SET object_key=excluded.object_key,confidence=excluded.confidence,'
          'reason=excluded.reason,updated_at=excluded.updated_at',
          [k.ad_id,obj.object_key,confidence,reason,ts]
        ))
        self.preferred[k.ad_id]=obj.object_key

    def audit(self,k):
        r=match_new(k,self.candidates)

        preferred=self.preferred.get(k.ad_id)
        independent={
          field:match_for_audit_field(k,self.candidates,field,preferred)
          for field in ('price','area')
        }
        mismatches={}; object_keys={}; reasons=[]

        # Keep address/floor/rooms as internal evidence, but never let the general
        # matcher alone create a price or area accusation.
        if r.obj:
            base=apply_mismatch_policy(k,r.obj,r.mismatches)
            for field,value in base.items():
                if field not in {'price','area'}:
                    mismatches[field]=value
                    object_keys[field]=r.obj.object_key
            reasons.append(r.reason)
        elif r.confidence=='AMBIGUOUS' and r.mismatches:
            for field,value in r.mismatches.items():
                if field not in {'price','area'}:
                    mismatches[field]=value
                    if r.reference: object_keys[field]=r.reference.object_key
            reasons.append(r.reason)

        identified={
          field:result.obj for field,result in independent.items() if result.obj
        }
        identity_keys={obj.object_key for obj in identified.values()}
        identity_conflict=len(identity_keys)>1

        if not identity_conflict:
            for field,result in independent.items():
                if not result.obj:
                    continue
                if vector(k,result.obj).get(field) is False:
                    value=result.mismatches.get(field)
                    if value:
                        mismatches[field]=value
                        object_keys[field]=result.obj.object_key
                reasons.append(result.reason)
        else:
            # Different objects for price and area mean that the card cannot be
            # identified safely enough for a red accusation.
            mismatches['review']=(
              'требуется проверка',
              'цена и площадь указывают на разные помещения BIR'
            )
            reasons.append('Independent price and area matching selected different BIR objects')

        if r.obj and r.confidence in {'EXACT','HIGH'}:
            matched_obj=r.obj
        else:
            matched_obj=next(iter(identified.values()),None) or r.obj or r.reference
        if r.obj and r.confidence in {'EXACT','HIGH'}:
            self.remember_match(k,r.obj,r.confidence,r.reason)
        elif matched_obj and not identity_conflict and identity_keys:
            self.remember_match(
              k,matched_obj,'FIELD_HIGH',
              '; '.join(result.reason for result in independent.values() if result.obj)
            )

        if mismatches:
            return {
              'status':'REVIEW' if set(mismatches)=={'review'} else 'MISMATCH',
              'ad_id':k.ad_id,
              'object_key':matched_obj.object_key if matched_obj else None,
              'object_keys':object_keys,
              'confidence':r.confidence,
              'reason':'; '.join(reasons) or r.reason,
              'mismatches':mismatches
            }

        # Two independent checks agreeing on the same object are enough to
        # resolve old events even when the address itself is unusable.
        if matched_obj and (r.obj or len(identified)>=2):
            if not resolved_bir_address(matched_obj):
                return {
                  'status':'REVIEW','ad_id':k.ad_id,'object_key':matched_obj.object_key,
                  'confidence':r.confidence,
                  'reason':'Для дома нет подтверждённого официального адреса',
                  'mismatches':{'review':('требуется проверка','нет адреса дома в справочнике')}
                }
            return {
              'status':'OK','ad_id':k.ad_id,'object_key':matched_obj.object_key,
              'confidence':r.confidence,'reason':'; '.join(reasons) or r.reason,
              'mismatches':{}
            }

        if not is_mw_claimed(k):
            return {'status':'OUT_OF_SCOPE','ad_id':k.ad_id,'reason':'No Minsk World marker and no Bir match','mismatches':{}}

        if r.confidence=='AMBIGUOUS':
            return {
              'status':'REVIEW','ad_id':k.ad_id,
              'object_key':r.reference.object_key if r.reference else None,
              'reason':r.reason,
              'mismatches':{'review':('требуется проверка','несколько равнозначных помещений BIR')}
            }

        historical=match_new(k,self.inactive_candidates)
        if historical.confidence=='AMBIGUOUS':
            return {
              'status':'REVIEW','ad_id':k.ad_id,'reason':'Historical Bir match is ambiguous',
              'mismatches':{'review':('требуется проверка','несколько архивных помещений BIR')}
            }

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
        elif status=='REVIEW':
            for field,(a,b) in mism.items():
                desired[field]=(str(a),str(b),'NEEDS_REVIEW')

        active=self.active.get(k.ad_id,{})
        new_events=[]

        for field,e in list(active.items()):
            if field not in desired:
                self.statements.append(('UPDATE events SET active=0,resolved_at=? WHERE id=?',[ts,e['id']]))
                del active[field]

        for field,(nv,bv,typ) in desired.items():
            sig=fp([k.ad_id,field,nv,bv]); cur=active.get(field)
            event_object_key=(result.get('object_keys') or {}).get(field,result.get('object_key'))
            if cur and cur.get('signature')==sig:
                continue
            if cur and cur.get('id') is not None:
                self.statements.append(('UPDATE events SET active=0,resolved_at=? WHERE id=?',[ts,cur['id']]))

            self.statements.append((
              'INSERT INTO events(ad_id,object_key,event_type,field_name,old_value,new_value,bir_value,active,occurred_at,signature) '
              'VALUES(?,?,?,?,?,?,?,?,?,?)',
              [k.ad_id,event_object_key,typ,field,cur.get('new_value') if cur else None,nv,bv,1,ts,sig]
            ))
            active[field]={
              'id':None,'ad_id':k.ad_id,'object_key':event_object_key,
              'event_type':typ,'field_name':field,'new_value':nv,'bir_value':bv,
              'signature':sig,'active':1,'occurred_at':ts
            }
            new_events.append({
              'event_type':typ,'field_name':field,'ad_id':k.ad_id,
              'old_value':cur.get('new_value') if cur else None,
              'new_value':nv,'bir_value':bv,'object_key':event_object_key,
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
    s=AuditSession(db,[k.ad_id]); r=s.audit(k); s.flush(); return r

def sync_events(db,k,result):
    s=AuditSession(db); out=s.sync(k,result); s.flush(); return out
