import asyncio
from collections import Counter
from radar.collectors.kufar import KufarCollector, is_mw_claimed
from radar.collectors.bir import BirCollector
from radar.matcher import match_new, vector

TARGETS=['1085587936','1085820441','1085809888','1085714847','1085699117']

async def main():
    k=KufarCollector(); ks=await k.collect()
    b=BirCollector(); bs=await b.collect()
    print('counts',{'kufar_alena':len(ks),'kufar_mw':sum(is_mw_claimed(x) for x in ks),'bir':len(bs),'bir_gps':sum(bool((x.raw or {}).get('gps')) for x in bs),'bir_address':sum(bool(x.official_address) for x in bs)})
    byid={x.ad_id:x for x in ks}
    print('\nTARGETS')
    for aid in TARGETS:
        x=byid.get(aid)
        if not x:
            print(aid,'MISSING'); continue
        r=match_new(x,bs)
        print(aid,{
          'k':{'eur':x.price_eur,'area':x.area,'rooms':x.rooms,'floor':x.floor,'address':x.address},
          'result':r.confidence,'reason':r.reason,
          'bir':None if not r.obj else {'key':r.obj.object_key,'building':r.obj.building_name,'address':r.obj.official_address,'gps':r.obj.raw.get('gps'),'unit':r.obj.unit_no,'reg':r.obj.price_regular_eur,'fast':r.obj.price_fast_eur,'area':r.obj.area,'rooms':r.obj.rooms,'floor':r.obj.floor},
          'vector':None if not r.obj else vector(x,r.obj),
          'mismatches':r.mismatches
        })

    stats=Counter(); mismatches=Counter()
    for x in [a for a in ks if is_mw_claimed(a)]:
        r=match_new(x,bs); stats[r.confidence]+=1
        if r.obj:
            for f in r.mismatches: mismatches[f]+=1
    print('\nSTATS',dict(stats))
    print('MISMATCH_FIELDS',dict(mismatches))
    print('bir_diag_tail',b.diagnostics[-3:])

if __name__=='__main__':
    asyncio.run(main())
