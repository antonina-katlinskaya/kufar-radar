import asyncio
from radar.collectors.kufar import KufarCollector
from radar.collectors.bir import BirCollector
from radar.matcher import match_new

TARGETS=['1085587936','1085820441','1085809888']

async def main():
    k=KufarCollector(); ks=await k.collect()
    b=BirCollector(); bs=await b.collect()
    print('counts',len(ks),len(bs))
    byid={x.ad_id:x for x in ks}
    for aid in TARGETS:
        x=byid.get(aid)
        print('\nTARGET',aid, x)
        if not x: continue
        r=match_new(x,bs)
        print('MATCH',r.confidence,r.reason,r.obj)
        print('MISMATCHES',r.mismatches)
        same_room_floor=[o for o in bs if o.rooms==x.rooms and o.floor==x.floor]
        same_room_floor.sort(key=lambda o:(abs((o.area or 9999)-(x.area or 0)), min(abs((o.price_fast_eur or 1e9)-(x.price_eur or 0)),abs((o.price_regular_eur or 1e9)-(x.price_eur or 0)))))
        print('NEAREST')
        for o in same_room_floor[:15]:
            print({'building':o.building_name,'unit':o.unit_no,'reg':o.price_regular_eur,'fast':o.price_fast_eur,'area':o.area,'rooms':o.rooms,'floor':o.floor,'cells':o.raw.get('cells'),'row_html':(o.raw.get('row_html') or '')[:1000]})
    print('\nALL 4-ROOM')
    for o in [x for x in bs if x.rooms==4]:
        print({'building':o.building_name,'unit':o.unit_no,'reg':o.price_regular_eur,'fast':o.price_fast_eur,'area':o.area,'floor':o.floor,'cells':o.raw.get('cells'),'html':(o.raw.get('row_html') or '')[:1200]})

if __name__=='__main__': asyncio.run(main())
