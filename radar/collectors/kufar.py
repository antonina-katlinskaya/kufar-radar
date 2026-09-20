import re, json, hashlib
from typing import Any
from playwright.async_api import async_playwright
from .common import walk_json, first_value
from ..config import settings
from ..models import KufarListing

MW_HINTS=('минск мир','minsk world','лученка','братская','аэродромная','алферова','алфёрова','старый аэропорт','брилевская','вирская','кижеватова','савицкого','белградская','левина')

def _num(v):
    if v is None: return None
    if isinstance(v,(int,float)): return float(v)
    s=str(v).replace('\xa0','').replace(' ','').replace(',','.')
    m=re.search(r'-?\d+(?:\.\d+)?',s); return float(m.group()) if m else None

def _int(v):
    n=_num(v); return int(n) if n is not None else None

def parse_ad_dict(d:dict[str,Any], profile_id:str):
    aid=first_value(d,['ad_id','adId','listingId','listing_id'])
    if aid is None: return None
    aid=str(aid)
    if not aid.isdigit() or len(aid)<8: return None
    url=first_value(d,['url','ad_link','link','canonicalUrl']) or f'https://re.kufar.by/vi/{aid}'
    return KufarListing(
      ad_id=aid,url=str(url),profile_id=profile_id,
      price_eur=_num(first_value(d,['priceEur','price_eur','price_eur_value','priceEUR'])),
      price_byn=_num(first_value(d,['priceByn','price_byn','priceBYN','price'])),
      area=_num(first_value(d,['area','square','total_area','size','square_meter'])),
      rooms=_int(first_value(d,['rooms','room_count','rms','rooms_count'])),
      floor=_int(first_value(d,['floor','floor_number','floorNumber'])),
      address=(str(first_value(d,['address','location_name','street','addressText'])) if first_value(d,['address','location_name','street','addressText']) else None),
      title=(str(first_value(d,['propertyTitle','title','subject','name'])) if first_value(d,['propertyTitle','title','subject','name']) else None),
      raw=d)

def is_scope(item:KufarListing):
    raw=json.dumps(item.raw,ensure_ascii=False).lower()
    text=' '.join([item.address or '',item.title or '',raw]).lower()
    return any(h in text for h in MW_HINTS)

class KufarCollector:
    def __init__(self): self.diagnostics=[]
    async def collect(self,max_scrolls=550):
        found={}
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=settings.headless)
            ctx=await browser.new_context(locale='ru-RU', user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36')
            page=await ctx.new_page()
            async def on_resp(resp):
                req=resp.request
                if req.resource_type not in {'xhr','fetch'}: return
                if 'kufar' not in resp.url and 'cre-api' not in resp.url: return
                ct=resp.headers.get('content-type','')
                self.diagnostics.append((resp.url,req.method,resp.status,ct))
                if 'json' not in ct: return
                try: data=await resp.json()
                except: return
                for d in walk_json(data):
                    item=parse_ad_dict(d,settings.kufar_profile_id)
                    if item: found[item.ad_id]=item
            page.on('response',on_resp)
            await page.goto(settings.kufar_profile_url,wait_until='domcontentloaded',timeout=90000)
            await page.wait_for_timeout(1800)
            stable=0; prev=-1
            for _ in range(max_scrolls):
                hrefs=await page.locator('a[href*="/vi/"]').evaluate_all('els=>els.map(e=>e.href)')
                for h in hrefs:
                    m=re.search(r'(\d{8,})(?:[/?#]|$)',h)
                    if m and m.group(1) not in found:
                        found[m.group(1)]=KufarListing(m.group(1),h,settings.kufar_profile_id)
                await page.mouse.wheel(0,14000); await page.wait_for_timeout(180)
                if len(found)==prev: stable+=1
                else: stable=0; prev=len(found)
                if stable>=12: break
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
