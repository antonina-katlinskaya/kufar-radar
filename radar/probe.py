import asyncio, json, re
from playwright.async_api import async_playwright
from radar.config import settings

def walk_paths(x,path='root'):
    if isinstance(x,dict):
        if isinstance(x.get('ads'),list):
            scalars={}
            for k,v in x.items():
                if isinstance(v,(str,int,float,bool)) or v is None:
                    scalars[k]=v
            yield path, len(x['ads']), list(x.keys()), scalars
        for k,v in x.items():
            yield from walk_paths(v,f'{path}.{k}')
    elif isinstance(x,list):
        for i,v in enumerate(x[:200]):
            yield from walk_paths(v,f'{path}[{i}]')

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(locale='ru-RU',user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36')
        pg=await ctx.new_page()
        await pg.goto(settings.kufar_profile_url,wait_until='domcontentloaded',timeout=90000)
        await pg.wait_for_timeout(1000)
        raw=await pg.locator('script#__NEXT_DATA__').text_content()
        data=json.loads(raw)
        print('=== ADS NODES ===')
        for row in walk_paths(data):
            print(row)
        print('=== ROUTER ===')
        try: print(json.dumps(data['props']['initialState']['router'],ensure_ascii=False))
        except Exception as e: print('router error',repr(e))
        body=await pg.locator('body').inner_text()
        print('=== PROFILE COUNTS ===')
        print(re.findall(r'\d[\d\s]*\s+объявлен\w*',body,re.I)[:20])

        print('=== JS ENDPOINT HITS ===')
        srcs=await pg.locator('script[src]').evaluate_all('els=>els.map(e=>e.src)')
        seen=0
        for src in srcs:
            if seen>=12: break
            try:
                r=await ctx.request.get(src,timeout=30000)
                txt=await r.text()
            except: continue
            for needle in ['rendered-paginated','cre-api.kufar.by','ads-search/v1','userId','accountId']:
                pos=txt.find(needle)
                if pos>=0:
                    print('SCRIPT',src,'NEEDLE',needle)
                    print(txt[max(0,pos-1200):pos+2500])
                    seen+=1
                    break
        await b.close()

if __name__=='__main__':
    asyncio.run(main())
