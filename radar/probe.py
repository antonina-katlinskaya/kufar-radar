import asyncio, re, json
import httpx
from radar.collectors.bir import BirCollector

BUILDINGS=['11.2','4.2','21.1','24.2.3']
TERMS=['лученка','теслы','брилев','аэропорт','адрес','address','coordinates','latitude','longitude','карта','map']

async def main():
    b=BirCollector(); bs=await b.collect()
    hrefs={}
    for name in BUILDINGS:
        x=next((o for o in bs if o.building_name==name and o.raw.get('house_href')),None)
        if x: hrefs[name]=x.raw.get('house_href')
    async with httpx.AsyncClient(timeout=40,follow_redirects=True,headers={'User-Agent':'Mozilla/5.0'}) as c:
        for name,href in hrefs.items():
            url='https://bir.by'+href if href.startswith('/') else 'https://bir.by/'+href.lstrip('/')
            r=await c.get(url); html=r.text
            print('\n===',name,url,'status',r.status_code,'len',len(html),'===')
            # meta / JSON-LD / attributes that may contain location.
            metas=re.findall(r'<meta[^>]+(?:name|property)=[\"\']([^\"\']+)[\"\'][^>]+content=[\"\']([^\"\']*)',html,re.I)
            for k,v in metas:
                if any(t in (k+' '+v).lower() for t in TERMS):
                    print('META',k,repr(v[:1000]))
            for m in re.finditer(r'<script[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>',html,re.I|re.S):
                print('JSONLD',m.group(1)[:4000])
            low=html.lower()
            for term in TERMS:
                starts=[m.start() for m in re.finditer(re.escape(term),low)]
                for pos in starts[:5]:
                    snippet=re.sub(r'\s+',' ',html[max(0,pos-700):pos+1400])
                    print('TERM',term,'CTX',snippet[:2200])
            # data-* attrs with address/coords/map-ish names
            for tag in re.findall(r'<[^>]+>',html,re.S):
                tl=tag.lower()
                if any(t in tl for t in ['data-address','data-lat','data-lon','data-coord','latitude','longitude']):
                    print('ATTR',re.sub(r'\s+',' ',tag)[:2200])

if __name__=='__main__': asyncio.run(main())
