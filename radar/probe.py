import asyncio
import httpx
from radar.config import settings

URL='https://cre-api.kufar.by/ads-search/v1/engine/v2/search/rendered-paginated'
BASE={'atid':settings.kufar_profile_id,'lang':'ru','size':'45','typ':'sell','prn':'1000','sort':'lst.d'}

async def main():
    async with httpx.AsyncClient(timeout=45,follow_redirects=True,headers={'User-Agent':'Mozilla/5.0'}) as c:
        r=await c.get(URL,params=BASE); d=r.json()
        first=d['ads'][0]['ad_id']; token=next(p['token'] for p in d['pagination']['pages'] if p.get('label')=='next')
        print('page1',r.status_code,'total',d.get('total'),'len',len(d.get('ads',[])),'first',first,'next',token)
        for key in ['cursor','token','page','cursor_token']:
            params=dict(BASE); params[key]=token if key!='page' else '2'
            rr=await c.get(URL,params=params)
            try: dd=rr.json()
            except: print(key,'nonjson',rr.status_code,rr.text[:300]); continue
            ads=dd.get('ads') or []
            print(key,'status',rr.status_code,'len',len(ads),'first',ads[0]['ad_id'] if ads else None,'same_as_page1',(ads[0]['ad_id']==first if ads else None),'pagination',dd.get('pagination'))

if __name__=='__main__':
    asyncio.run(main())
