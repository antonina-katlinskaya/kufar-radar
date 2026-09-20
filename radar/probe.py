import asyncio
from collections import Counter
from radar.collectors.kufar import KufarCollector, is_mw_claimed
from radar.collectors.bir import BirCollector
from radar.matcher import match_new

TARGETS=['1085587936','1085820441','1085809888']

async def main():
    k=KufarCollector(); ks=await k.collect()
    b=BirCollector(); bs=await b.collect()
    print('kufar_alena',len(ks))
    print('kufar_mw_claimed',sum(is_mw_claimed(x) for x in ks))
    print('bir',len(bs),'bir_with_address',sum(bool(x.official_address) for x in bs))
    print('kufar_last_diag',k.diagnostics[-10:])

    byid={x.ad_id:x for x in ks}
    print('\nTARGETS')
    for aid in TARGETS:
        x=byid.get(aid)
        if not x:
            print(aid,'MISSING'); continue
        r=match_new(x,bs)
        print(aid,{
          'kufar':{'eur':x.price_eur,'area':x.area,'rooms':x.rooms,'floor':x.floor,'address':x.address,'mw':is_mw_claimed(x)},
          'result':r.confidence,'reason':r.reason,
          'bir':None if not r.obj else {'key':r.obj.object_key,'building':r.obj.building_name,'address':r.obj.official_address,'unit':r.obj.unit_no,'reg':r.obj.price_regular_eur,'fast':r.obj.price_fast_eur,'area':r.obj.area,'rooms':r.obj.rooms,'floor':r.obj.floor},
          'mismatches':r.mismatches
        })

    print('\nDRY AUDIT MW-CLAIMED')
    stats=Counter(); anomalies=[]
    for x in [a for a in ks if is_mw_claimed(a)]:
        r=match_new(x,bs)
        stats[r.confidence]+=1
        if r.obj and r.mismatches:
            anomalies.append((x,r))
    print('stats',dict(stats))
    print('matched_with_mismatches',len(anomalies))
    for x,r in anomalies[:30]:
        print({'id':x.ad_id,'k':{'eur':x.price_eur,'area':x.area,'rooms':x.rooms,'floor':x.floor,'address':x.address},'confidence':r.confidence,'bir':{'building':r.obj.building_name,'address':r.obj.official_address,'unit':r.obj.unit_no,'reg':r.obj.price_regular_eur,'fast':r.obj.price_fast_eur,'area':r.obj.area,'rooms':r.obj.rooms,'floor':r.obj.floor},'mismatches':r.mismatches})

if __name__=='__main__': asyncio.run(main())
