import asyncio, re
import httpx
from radar.collectors.bir import BirCollector

BUILDINGS=['11.2','4.2','21.1','24.2.3']

async def main():
    b=BirCollector(); bs=await b.collect()
    print('objects',len(bs))
    hrefs={}
    for name in BUILDINGS:
        xs=[x for x in bs if x.building_name==name]
        print('\nBUILDING',name,'count',len(xs))
        for x in xs[:2]:
            print({'address':x.official_address,'href':x.raw.get('house_href'),'cells':x.raw.get('cells')})
            if x.raw.get('house_href'): hrefs[name]=x.raw.get('house_href')
    async with httpx.AsyncClient(timeout=40,follow_redirects=True,headers={'User-Agent':'Mozilla/5.0'}) as c:
        for name,href in hrefs.items():
            url='https://bir.by'+href if href.startswith('/') else 'https://bir.by/'+href.lstrip('/')
            r=await c.get(url)
            text=re.sub(r'<script[\s\S]*?</script>',' ',r.text,flags=re.I)
            text=re.sub(r'<style[\s\S]*?</style>',' ',text,flags=re.I)
            plain=re.sub(r'<[^>]+>',' ',text)
            plain=' '.join(plain.replace('&nbsp;',' ').split())
            print('\nPAGE',name,url,r.status_code,'title-ish',plain[:800])
            for pat in ['улица','ул.','проспект','дом','Адрес','адрес']:
                i=plain.find(pat)
                if i>=0: print('CONTEXT',plain[max(0,i-300):i+800]); break

if __name__=='__main__': asyncio.run(main())
