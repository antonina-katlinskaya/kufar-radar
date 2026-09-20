import asyncio, json, re
from playwright.async_api import async_playwright
from radar.collectors.kufar import KufarCollector, parse_ad_dict
from radar.collectors.bir import BirCollector
from radar.collectors.common import walk_json
from radar.config import settings

async def inspect_kufar_next_data():
    print('=== KUFAR NEXT DATA ===')
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        pg=await b.new_page(locale='ru-RU')
        await pg.goto(settings.kufar_profile_url,wait_until='domcontentloaded',timeout=90000)
        await pg.wait_for_timeout(1200)
        raw=await pg.locator('script#__NEXT_DATA__').text_content()
        data=json.loads(raw)
        ads=[]
        for d in walk_json(data):
            x=parse_ad_dict(d,settings.kufar_profile_id)
            if x and x.ad_id not in {a.ad_id for a in ads}: ads.append(x)
        print('NEXT ads:',len(ads))
        for a in ads[:5]:
            print('NEXT AD:',a)
            print('RAW KEYS:',sorted(a.raw.keys())[:120])
        hrefs=await pg.locator('a[href*="/agency?userId=11093294&cursor="]').evaluate_all('els=>els.map(e=>e.href)')
        print('cursor hrefs:',hrefs[:10])
        if hrefs:
            await pg.goto(hrefs[0],wait_until='domcontentloaded',timeout=90000)
            await pg.wait_for_timeout(800)
            raw2=await pg.locator('script#__NEXT_DATA__').text_content()
            data2=json.loads(raw2)
            ads2=[]
            for d in walk_json(data2):
                x=parse_ad_dict(d,settings.kufar_profile_id)
                if x and x.ad_id not in {a.ad_id for a in ads2}: ads2.append(x)
            print('PAGE2 NEXT ads:',len(ads2))
            print('PAGE2 first:',ads2[:3])
        # Inspect one known detail page.
        target='https://re.kufar.by/vi/minsk/kupit/kvartiru/v-novostrojke/bez-otdelki/1085587936'
        await pg.goto(target,wait_until='domcontentloaded',timeout=90000)
        await pg.wait_for_timeout(800)
        if await pg.locator('script#__NEXT_DATA__').count():
            rd=await pg.locator('script#__NEXT_DATA__').text_content()
            dd=json.loads(rd)
            hits=[]
            for d in walk_json(dd):
                if str(d.get('ad_id') or d.get('adId') or d.get('listingId') or '')=='1085587936':
                    hits.append(d)
            print('DETAIL dict hits:',len(hits))
            for h in hits[:3]:
                print('DETAIL keys:',sorted(h.keys()))
                print('DETAIL:',json.dumps(h,ensure_ascii=False)[:12000])
        await b.close()

async def main():
    await inspect_kufar_next_data()
    print('=== KUFAR COLLECTOR ===')
    k=KufarCollector(); items=await k.collect(); print('count:',len(items)); print('first:',items[:10]); print('diagnostics:',k.diagnostics[-20:])
    print('=== BIR COLLECTOR ===')
    b=BirCollector(); items2=await b.collect(); print('count:',len(items2)); print('first:',items2[:12]); print('rooms counts:',{n:sum(1 for x in items2 if x.rooms==n) for n in range(1,6)}); print('diagnostics:',b.diagnostics[-20:])

if __name__=='__main__': asyncio.run(main())
\n# probe trigger v3\n