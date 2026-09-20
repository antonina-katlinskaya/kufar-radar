import re, json, base64
from urllib.parse import urlparse, parse_qs, unquote
from typing import Any
from playwright.async_api import async_playwright
from .common import walk_json, first_value
from ..config import settings
from ..models import KufarListing

MW_HINTS=('минск мир','minsk world','лученка','братская','аэродромная','алферова','алфёрова','старый аэропорт','брилевская','вирская','кижеватова','савицкого','белградская','левина','минск-мир')

def _num(v):
    if v is None: return None
    if isinstance(v,(int,float)): return float(v)
    s=str(v).replace('\xa0','').replace(' ','').replace(',','.')
    m=re.search(r'-?\d+(?:\.\d+)?',s)
    return float(m.group()) if m else None

def _int(v):
    n=_num(v); return int(n) if n is not None else None

def parse_ad_dict(d:dict[str,Any], profile_id:str):
    aid=first_value(d,['ad_id','adId','listingId','listing_id'])
    if aid is None: return None
    aid=str(aid)
    if not aid.isdigit() or len(aid)<8: return None
    url=first_value(d,['url','ad_link','link','canonicalUrl','ad_url']) or f'https://re.kufar.by/vi/{aid}'
    return KufarListing(
      ad_id=aid,url=str(url),profile_id=profile_id,
      price_eur=_num(first_value(d,['priceEur','price_eur','price_eur_value','priceEUR','price_eur_amount'])),
      price_byn=_num(first_value(d,['priceByn','price_byn','priceBYN','price','price_byn_amount'])),
      area=_num(first_value(d,['area','square','total_area','size','square_meter','square_meters'])),
      rooms=_int(first_value(d,['rooms','room_count','rms','rooms_count','rooms_num'])),
      floor=_int(first_value(d,['floor','floor_number','floorNumber'])),
      address=(str(first_value(d,['address','location_name','street','addressText','address_text'])) if first_value(d,['address','location_name','street','addressText','address_text']) else None),
      title=(str(first_value(d,['propertyTitle','title','subject','name','ad_title'])) if first_value(d,['propertyTitle','title','subject','name','ad_title']) else None),
      raw=d)

def is_scope(item:KufarListing):
    raw=json.dumps(item.raw,ensure_ascii=False).lower()
    text=' '.join([item.address or '',item.title or '',raw]).lower()
    return any(h in text for h in MW_HINTS)

def _cursor_page(url):
    try:
        q=parse_qs(urlparse(url).query); c=q.get('cursor',[None])[0]
        if not c: return None
        raw=base64.b64decode(unquote(c)).decode()
        return int(json.loads(raw).get('p'))
    except: return None

async def _page_ads(page):
    out={}
    if await page.locator('script#__NEXT_DATA__').count():
        try:
            data=json.loads(await page.locator('script#__NEXT_DATA__').text_content())
            for d in walk_json(data):
                x=parse_ad_dict(d,settings.kufar_profile_id)
                if x:
                    old=out.get(x.ad_id)
                    # Prefer the richest copy of the same ad.
                    if old is None or len(json.dumps(x.raw,ensure_ascii=False))>len(json.dumps(old.raw,ensure_ascii=False)):
                        out[x.ad_id]=x
        except Exception:
            pass
    hrefs=await page.locator('a[href*="/vi/"]').evaluate_all('els=>els.map(e=>e.href)')
    for h in hrefs:
        m=re.search(r'(\d{8,})(?:[/?#]|$)',h)
        if m and m.group(1) not in out:
            out[m.group(1)]=KufarListing(m.group(1),h,settings.kufar_profile_id)
        elif m and m.group(1) in out and '/vi/' in h:
            out[m.group(1)].url=h
    return out

class KufarCollector:
    def __init__(self): self.diagnostics=[]
    async def collect(self,max_pages=100):
        found={}
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=settings.headless)
            ctx=await browser.new_context(locale='ru-RU', user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36')
            page=await ctx.new_page()
            url=settings.kufar_profile_url
            seen_urls=set()
            for page_no in range(1,max_pages+1):
                if url in seen_urls: break
                seen_urls.add(url)
                resp=await page.goto(url,wait_until='domcontentloaded',timeout=90000)
                await page.wait_for_timeout(500)
                self.diagnostics.append((url,'GET',resp.status if resp else None,(resp.headers.get('content-type','') if resp else ''),f'page={page_no}'))
                batch=await _page_ads(page)
                before=len(found); found.update(batch)
                links=await page.locator('a[href*="/agency?userId="][href*="cursor="]').evaluate_all('els=>els.map(e=>e.href)')
                options=[(_cursor_page(h),h) for h in links]
                options=[x for x in options if x[0] is not None and x[0]>page_no]
                if not options: break
                options.sort(key=lambda x:x[0])
                url=options[0][1]
                if len(found)==before and page_no>2: break

            # Keep Minsk World ads when the embedded data is rich enough to identify them.
            scoped=[x for x in found.values() if is_scope(x)]
            result=scoped if scoped else list(found.values())
            await browser.close()
        return result

async def screenshot_ad(url,path):
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True); pg=await b.new_page(viewport={'width':1440,'height':1100})
        try:
            await pg.goto(url,wait_until='domcontentloaded',timeout=60000); await pg.wait_for_timeout(1200)
            await pg.screenshot(path=path,full_page=True)
            return True
        except: return False
        finally: await b.close()
