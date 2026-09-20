import asyncio
from radar.collectors.kufar import KufarCollector, contact_person
from radar.collectors.bir import BirCollector

async def main():
    print('=== KUFAR ===')
    k=KufarCollector()
    items=await k.collect()
    print('count:',len(items))
    for x in items[:20]:
        print({
          'ad_id':x.ad_id,'eur':x.price_eur,'byn':x.price_byn,
          'area':x.area,'rooms':x.rooms,'floor':x.floor,
          'address':x.address,'contact':contact_person(x),'title':x.title
        })
    print('kufar diagnostics:')
    for d in k.diagnostics[-20:]: print(d)

    print('=== BIR ===')
    b=BirCollector()
    items2=await b.collect()
    print('count:',len(items2))
    print('rooms counts:',{n:sum(1 for x in items2 if x.rooms==n) for n in range(1,6)})
    for x in items2[:20]:
        print({
          'key':x.object_key,'building':x.building_name,'unit':x.unit_no,
          'eur_regular':x.price_regular_eur,'eur_fast':x.price_fast_eur,
          'area':x.area,'rooms':x.rooms,'floor':x.floor
        })
    print('bir diagnostics:')
    for d in b.diagnostics[-20:]: print(d)

if __name__=='__main__':
    asyncio.run(main())
