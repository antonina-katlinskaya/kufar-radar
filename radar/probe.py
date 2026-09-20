import asyncio, json
from playwright.async_api import async_playwright
from radar.config import settings

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True)
        ctx=await b.new_context(locale='ru-RU',user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36')
        pg=await ctx.new_page()
        requests=[]; responses=[]
        def on_req(r):
            if 'bir.by' in r.url and r.resource_type in {'xhr','fetch'}:
                requests.append((r.url,r.method,r.post_data))
        async def on_resp(r):
            if 'bir.by' in r.url and r.request.resource_type in {'xhr','fetch'}:
                try: body=(await r.text())[:5000]
                except: body=''
                responses.append((r.url,r.status,r.headers.get('content-type',''),body))
        pg.on('request',on_req); pg.on('response',on_resp)
        await pg.goto(settings.bir_search_url,wait_until='domcontentloaded',timeout=90000)
        await pg.wait_for_timeout(800)
        rows=pg.locator('tr.loadobject')
        print('rows',await rows.count())
        if await rows.count():
            row=rows.first
            print('row_id',await row.get_attribute('data-loadobject'))
            print('row_text',' '.join((await row.inner_text()).split()))
            await row.click(timeout=5000)
            await pg.wait_for_timeout(1600)
            print('modal_address', await pg.locator('.modal-adres').inner_text() if await pg.locator('.modal-adres').count() else 'NO')
        print('REQUESTS')
        for x in requests: print(x)
        print('RESPONSES')
        for x in responses: print(x)
        await b.close()

if __name__=='__main__': asyncio.run(main())
