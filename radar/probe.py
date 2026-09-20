import asyncio, re, json
from playwright.async_api import async_playwright
from radar.collectors.kufar import KufarCollector
from radar.collectors.bir import BirCollector
from radar.config import settings

async def inspect_kufar_page():
    print('=== KUFAR PAGE DIAGNOSTICS ===')
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        pg=await b.new_page(locale='ru-RU')
        await pg.goto(settings.kufar_profile_url,wait_until='domcontentloaded',timeout=90000)
        await pg.wait_for_timeout(2000)
        print('title:', await pg.title())
        print('url:', pg.url)
        print('buttons:', (await pg.locator('button').all_inner_texts())[:80])
        hrefs=await pg.locator('a').evaluate_all('els=>els.map(e=>e.href).filter(Boolean)')
        print('href count:',len(hrefs))
        print('pagination-ish hrefs:', [h for h in hrefs if 'page=' in h.lower() or 'cursor' in h.lower()][:50])
        scripts=await pg.locator('script').all_text_contents()
        hits=[]
        for s in scripts:
            if '11093294' in s or '1085587936' in s or 'pagination' in s.lower() or 'cursor' in s.lower():
                hits.append(s[:7000])
        print('script hits:',len(hits))
        for i,s in enumerate(hits[:8]): print(f'--- script {i} ---\\n{s[:7000]}')
        await b.close()

async def inspect_bir_request():
    print('=== BIR REQUEST DIAGNOSTICS ===')
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        pg=await b.new_page(locale='ru-RU')
        seen=[]
        def req(r):
            if 'get-search-objects-new' in r.url:
                seen.append((r.url,r.method,r.post_data))
        pg.on('request',req)
        await pg.goto(settings.bir_search_url,wait_until='domcontentloaded',timeout=90000)
        await pg.wait_for_timeout(1000)
        btn=pg.get_by_text('Показать ещё 15 вариантов',exact=False)
        if await btn.count():
            try: await btn.first.click(timeout=3000); await pg.wait_for_timeout(1000)
            except Exception as e: print('click error',repr(e))
        print('requests:', seen[-5:])
        # Inputs used by room filters, to learn exact parameter names/values.
        inputs=await pg.locator('input').evaluate_all("els=>els.map(e=>({name:e.name,value:e.value,type:e.type,checked:e.checked,id:e.id})).filter(x=>x.name||x.id)")
        print('inputs:', json.dumps(inputs[:250],ensure_ascii=False))
        await b.close()

async def main():
    await inspect_kufar_page()
    await inspect_bir_request()
    print('=== KUFAR PROBE ===')
    k=KufarCollector(); items=await k.collect(); print('count:',len(items)); print('first:',items[:5]); print('diagnostics:',k.diagnostics[-20:])
    print('=== BIR PROBE ===')
    b=BirCollector(); items2=await b.collect(); print('count:',len(items2)); print('first:',items2[:10]); print('diagnostics:',b.diagnostics[-20:])

if __name__=='__main__': asyncio.run(main())
