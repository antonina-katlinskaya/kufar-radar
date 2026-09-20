import asyncio, json
import httpx
from radar.collectors.bir import BirCollector

DETAIL='https://bir.by/ajax/get-object-by-tablerow-click/'
TARGET_BUILDINGS=['11.2','4.2','21.1','24.2.3']

async def main():
    b=BirCollector()
    items=await b.collect()
    print('objects',len(items))
    async with httpx.AsyncClient(timeout=40,follow_redirects=True,headers={
        'User-Agent':'Mozilla/5.0',
        'X-Requested-With':'XMLHttpRequest',
        'Referer':'https://bir.by/search-by-parameters/',
        'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8',
    }) as c:
        for name in TARGET_BUILDINGS:
            x=next((o for o in items if o.building_name==name),None)
            if not x:
                print('MISSING_BUILDING',name); continue
            r=await c.post(DETAIL,data={'objectid':x.object_key})
            print('\n===',name,x.object_key,'status',r.status_code,'ct',r.headers.get('content-type'),'===')
            try:
                d=r.json()
            except Exception as e:
                print('NONJSON',repr(e),r.text[:500]); continue
            print('keys',sorted(d.keys()))
            compact={}
            for k,v in d.items():
                kl=k.lower()
                if k=='image' or (isinstance(v,str) and len(v)>1000):
                    continue
                if isinstance(v,(str,int,float,bool)) or v is None:
                    compact[k]=v
            print('scalars',json.dumps(compact,ensure_ascii=False,sort_keys=True))
            addressish={k:v for k,v in compact.items() if any(t in k.lower() for t in ['adres','address','street','ulitsa','dom','house','korpus','coord','lat','lon'])}
            print('addressish',json.dumps(addressish,ensure_ascii=False,sort_keys=True))

if __name__=='__main__':
    asyncio.run(main())
