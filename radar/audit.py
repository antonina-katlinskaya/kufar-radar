import json
from .matcher import (
    apply_mismatch_policy,match_for_audit_field,match_new,mismatch_map,vector
)
from .house_directory import resolved_bir_address
from .store import fp, now, current_bir, inactive_bir
from .collectors.kufar import is_mw_claimed
from .config import settings

TRUSTED_PASSPORT_CONFIDENCE={'EXACT','HIGH'}

def _same_value(a,b):
    if a is None or b is None:
        return a is b
    try:
        return float(a)==float(b)
    except (TypeError,ValueError):
        return str(a).strip().casefold()==str(b).strip().casefold()

def _raw_dict(value):
    if isinstance(value,dict): return value
    try:
        parsed=json.loads(value or '{}')
        return parsed if isinstance(parsed,dict) else {}
    except (TypeError,ValueError):
        return {}

def _primary_image_id(version):
    return _raw_dict((version or {}).get('raw_json')).get('primary_image_id')

def listing_replaced(recent_versions):
    """Detect a real card repurpose without treating address/price edits as identity changes."""
    if len(recent_versions or [])<2:
        return False
    latest,previous=recent_versions[0],recent_versions[1]
    core_changes=sum(
      not _same_value(latest.get(field),previous.get(field))
      for field in ('area','rooms','floor')
    )
    if core_changes>=2:
        return True
    title_changed=not _same_value(latest.get('title'),previous.get('title'))
    latest_image=_primary_image_id(latest)
    previous_image=_primary_image_id(previous)
    image_changed=bool(
      latest_image and previous_image and latest_image!=previous_image
    )
    return core_changes>=1 and title_changed and image_changed

class AuditSession:
    def __init__(self, db, ad_ids=None):
        self.db=db
        self.candidates=current_bir(db)
        self.inactive_candidates=inactive_bir(db)
        self.active={}
        for r in db.query('SELECT * FROM events WHERE active=1 AND occurred_at >= ?',[settings.live_cutoff_utc]):
            self.active.setdefault(r['ad_id'],{})[r['field_name']]=r
        self.preferred={}
        self.passport_confidence={}
        self.passport_updated_at={}
        self.recent_versions={}
        wanted=list(dict.fromkeys(str(ad_id) for ad_id in (ad_ids or [])))
        if wanted:
            for i in range(0,len(wanted),75):
                chunk=wanted[i:i+75]
                marks=','.join('?' for _ in chunk)
                for r in db.query(
                  f'''SELECT ad_id,object_key,confidence,updated_at
                      FROM matches WHERE ad_id IN ({marks})''',chunk
                ):
                    if r.get('ad_id') is not None and r.get('object_key') is not None:
                        ad_id=str(r['ad_id'])
                        self.preferred[ad_id]=str(r['object_key'])
                        self.passport_confidence[ad_id]=str(r.get('confidence') or '')
                        self.passport_updated_at[ad_id]=r.get('updated_at')
                version_rows=db.query(
                  f'''SELECT * FROM (
                        SELECT v.*, ROW_NUMBER() OVER (
                          PARTITION BY ad_id ORDER BY id DESC
                        ) AS recent_rank
                        FROM kufar_versions v WHERE ad_id IN ({marks})
                      ) WHERE recent_rank<=2 ORDER BY ad_id,recent_rank''',chunk
                )
                for row in version_rows:
                    self.recent_versions.setdefault(str(row['ad_id']),[]).append(row)
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
        self.passport_confidence[k.ad_id]=confidence
        self.passport_updated_at[k.ad_id]=ts

    def forget_match(self,ad_id,reason):
        self.statements.append(('DELETE FROM matches WHERE ad_id=?',[ad_id]))
        self.preferred.pop(ad_id,None)
        self.passport_confidence.pop(ad_id,None)
        self.passport_updated_at.pop(ad_id,None)
        return reason

    def passport_predates_latest_version(self,ad_id):
        versions=getattr(self,'recent_versions',{}).get(ad_id,[])
        if not versions:
            return False
        latest_at=versions[0].get('observed_at')
        matched_at=getattr(self,'passport_updated_at',{}).get(ad_id)
        if not latest_at or not matched_at:
            return True
        return str(latest_at)>str(matched_at)

    def audit(self,k):
        r=match_new(k,self.candidates)

        preferred=self.preferred.get(k.ad_id)
        trusted=(
          preferred is not None and
          getattr(self,'passport_confidence',{}).get(k.ad_id) in TRUSTED_PASSPORT_CONFIDENCE
        )
        replacement_reason=None
        if (
          trusted and self.passport_predates_latest_version(k.ad_id) and
          listing_replaced(getattr(self,'recent_versions',{}).get(k.ad_id,[]))
        ):
            replacement_reason=self.forget_match(
              k.ad_id,'Kufar card identity changed; previous BIR passport discarded'
            )
            preferred=None; trusted=False

        passport_obj=next(
          (obj for obj in self.candidates if trusted and obj.object_key==preferred),None
        )
        independent={
          field:match_for_audit_field(
            k,self.candidates,field,preferred if passport_obj else None
          )
          for field in ('price','area')
        }
        mismatches={}; object_keys={}; reasons=[]

        # If both independent audits identify the same *different* object, the
        # old Kufar ID has been repurposed even when rooms/floor happen to match.
        independent_objects=[result.obj for result in independent.values() if result.obj]
        strong_new_object=(
          passport_obj and r.obj and r.confidence in {'EXACT','HIGH'} and
          r.obj.object_key!=passport_obj.object_key
        )
        independent_new_object=False
        if passport_obj and len(independent_objects)==2:
            new_keys={obj.object_key for obj in independent_objects}
            independent_new_object=(
              len(new_keys)==1 and passport_obj.object_key not in new_keys
            )
        if passport_obj and (strong_new_object or independent_new_object):
            replacement_reason=self.forget_match(
              k.ad_id,'Current card confidently identifies a new BIR object'
            )
            passport_obj=None; preferred=None; trusted=False

        if replacement_reason:
            reasons.append(replacement_reason)

        # A trusted passport is the primary identity source. Address changes do
        # not break it; price/area are compared directly with the same BIR unit.
        if passport_obj:
            passport_mismatches=apply_mismatch_policy(
              k,passport_obj,mismatch_map(k,passport_obj)
            )
            for field,value in passport_mismatches.items():
                mismatches[field]=value
                object_keys[field]=passport_obj.object_key
            reasons.append('Trusted Kufar-to-BIR object passport')
            if mismatches:
                return {
                  'status':'MISMATCH','ad_id':k.ad_id,
                  'object_key':passport_obj.object_key,'object_keys':object_keys,
                  'confidence':'PASSPORT','reason':'; '.join(reasons),
                  'mismatches':mismatches
                }
            return {
              'status':'OK','ad_id':k.ad_id,'object_key':passport_obj.object_key,
              'confidence':'PASSPORT','reason':'; '.join(reasons),'mismatches':{}
            }

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

        if mismatches:
            actionable={field for field in mismatches if field in {'price','area'}}
            confirmed_by_general_match={
              field for field in actionable
              if r.obj and r.confidence in {'EXACT','HIGH'} and
              object_keys.get(field)==r.obj.object_key
            }
            status=(
              'REVIEW' if set(mismatches)=={'review'} else
              'PROBABLE' if actionable-confirmed_by_general_match else
              'MISMATCH'
            )
            return {
              'status':status,
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
        elif status in {'MISMATCH','PROBABLE'}:
            mismatch_type='PROBABLE_MISMATCH' if status=='PROBABLE' else 'NEW_MISMATCH'
            for field,(a,b) in mism.items():
                desired[field]=(
                  str(a),json.dumps(b,ensure_ascii=False) if isinstance(b,(dict,list)) else str(b),
                  mismatch_type
                )
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
                if cur.get('event_type')!=typ and cur.get('id') is not None:
                    self.statements.append((
                      'UPDATE events SET event_type=?,object_key=? WHERE id=?',
                      [typ,event_object_key,cur['id']]
                    ))
                    cur['event_type']=typ
                    cur['object_key']=event_object_key
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
