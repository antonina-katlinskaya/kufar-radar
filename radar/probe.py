import asyncio
from radar.collectors.kufar import KufarCollector, contact_person, is_mw_claimed
from radar.collectors.bir import BirCollector

TARGET='1085587936'

async def main():
    print('=== KUFAR FULL MANAGER ===')
    k=KufarCollector(); items=await k.collect()
    print('alena_count',len(items))
    print('mw_claimed_count',sum(1 for x in items if is_mw_claimed(x)))
    print('target_present',any(x.ad_id==TARGET for x in items))
    target=next((x for x in items if x.ad_id==TARGET),None)
    if target:
        print('target',{'id':target.ad_id,'eur':target.price_eur,'area':target.area,'rooms':target.rooms,'floor':target.floor,'address':target.address,'title':target.title})
    print('sample')
    for x in items[:12]:
        print({'id':x.ad_id,'eur':x.price_eur,'area':x.area,'rooms':x.rooms,'floor':x.floor,'address':x.address,'mw':is_mw_claimed(x)})
    print('pages',len(k.diagnostics),'last',k.diagnostics[-3:])

    print('=== BIR ===')
    b=BirCollector(); items2=await b.collect()
    print('bir_count',len(items2))
    print('rooms',{n:sum(1 for x in items2 if x.rooms==n) for n in range(1,6)})
    print('target_like',[{'building':x.building_name,'unit':x.unit_no,'reg':x.price_regular_eur,'fast':x.price_fast_eur,'area':x.area,'rooms':x.rooms,'floor':x.floor} for x in items2 if x.rooms==1 and x.floor==2 and x.area is not None and 30.30<=x.area<=30.50 and (x.price_fast_eur==43669 or x.price_regular_eur==43669)][:20])
    print('bir_diag',b.diagnostics)

if __name__=='__main__': asyncio.run(main())
