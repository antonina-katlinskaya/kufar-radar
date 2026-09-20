import asyncio, json, re
import httpx
from playwright.async_api import async_playwright
from radar.config import settings

API_CANDIDATES=[
  'https://cre-api.kufar.by/ads-search/v1/engine/v2/search/rendered-paginated',
  'https://cre-api.kufar.by/ads-search/v1/engine/v1/search/rendered-paginated',
]

async def test_api():
    print('=== DIRECT API CANDIDATES ===')
    params={'atid':settings.kufar_profile_id,'lang':'ru','size':'45','typ':'sell','prn':'1000','sort':'lst.d'}
    async with httpx.AsyncClient(timeout=45,follow_redirects=True,headers={'User-Agent':'Mozilla/5.0'}) as c:
        for url in API_CANDIDATES:
            try:
                r=await c.get(url,params=params)
                print('URL',str(r.url),'STATUS',r.status_code,'CT',r.headers.get('content-type'))
                print('HEAD',r.text[:800].replace('\n',' '))
                if 'json' in r.headers.get('content-type',''):
                    d=r.json()
                    print('KEYS',list(d.keys()) if isinstance(d,dict) else type(d).__name__)
                    if isinstance(d,dict):
                        for k in ['total','count','pagination','cursor','search_id','searchId']:
                            if k in d: print(k, d[k])
                        print('ads_len',len(d.get('ads') or []))
                        if d.get('ads'):
                            print('first_ad_keys',list(d['ads'][0].keys())[:100])
            except Exception as e:
                print('ERR',url,repr(e))

async def inspect_bundle():
    print('=== BUNDLE ACTION HITS ===')
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(locale='ru-RU')
        pg=await ctx.new_page()
        await pg.goto(settings.kufar_profile_url,wait_until='domcontentloaded',timeout=90000)
        await pg.wait_for_timeout(500)
        srcs=await pg.locator('script[src]').evaluate_all('els=>els.map(e=>e.src).filter(s=>s.includes("content.kufar.by"))')
        for src in srcs:
            try:
                rr=await ctx.request.get(src,timeout=30000)
                txt=await rr.text()
            except: continue
            for needle in ['getAccountLandingPageAds','rendered-paginated','accountLandingPage']:
                pos=txt.find(needle)
                if pos>=0:
                    print('SCRIPT',src,'NEEDLE',needle)
                    print(txt[max(0,pos-1800):pos+4500])
        await b.close()

async def main():
    await test_api()
    await inspect_bundle()

if __name__=='__main__':
    asyncio.run(main())
