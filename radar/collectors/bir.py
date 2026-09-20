import re, hashlib
from typing import Any
from playwright.async_api import async_playwright
from .common import walk_json, first_value
from ..config import settings
from ..models import BirListing

def _num(v):
    if v is None: return None
    if isinstance(v,(int,float)): return float(v)
    s=str(v).replace('\xa0','').replace(' ','').replace(',','.')
    m=re.search(r'-?\d+(?:\.\d+)?',s); return float(m.group()) if m else None

def _int(v):
    n=_num(v); return int(n) if n is not None else None

def make_key(building,unit,floor,area):
    return hashlib.sha1(f'{building or ""}|{unit or ""}|{floor or ""}|{area or ""}'.encode()).hexdigest()

def parse_bir_dict(d:dict[str,Any]):
    building=first_value(d,['building_name','object_name','house_name','name','title'])
    unit=first_value(d,['unit','unit_no','room_number','number','flat_number','premise_number'])
    floor=_int(first_value(d,['floor','floor_number']))
    area=_num(first_value(d,['area','square','total_area']))
    if unit is None or floor is None or area is None or area<=0: return None
    return BirListing(
      object_key=make_key(str(building) if building else None,str(unit),floor,area),
      building_name=str(building) if building else None,
      official_address=(str(first_value(d,['address','official_address','house_address'])) if first_value(d,['address','official_address','house_address']) else None),
      unit_no=str(unit),
      price_regular_eur=_num(first_value(d,['price_eur','regular_price_eur','installment_price_eur','total_price_eur'])),
      price_fast_eur=_num(first_value(d,['special_price_eur','fast_price_eur','special_total_eur','quick_payment_price_eur'])),
      area=area,rooms=_int(first_value(d,['rooms','room_count','rooms_count'])),floor=floor,raw=d)

class BirCollector:
    def __init__(self): self.diagnostics=[]
    async def collect(self,max_clicks=400):
        found={}
        async with async_playwright() as p:
            b=await p.chromium.launch(headless=settings.headless)
            ctx=await b.new_context(locale='ru-RU', user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36')
            page=await ctx.new_page()
            async def on_resp(resp):
                req=resp.request
                if req.resource_type not in {'xhr','fetch'} or 'bir.by' not in resp.url: return
                ct=resp.headers.get('content-type',''); self.diagnostics.append((resp.url,req.method,resp.status,ct))
                if 'json' not in ct: return
                try: data=await resp.json()
                except: return
                for d in walk_json(data):
                    x=parse_bir_dict(d)
                    if x: found[x.object_key]=x
            page.on('response',on_resp)
            await page.goto(settings.bir_search_url,wait_until='domcontentloaded',timeout=90000)
            await page.wait_for_timeout(1200)
            for i in range(max_clicks):
                btn=page.get_by_text('Показать ещё 15 вариантов',exact=False)
                if await btn.count()==0: break
                try:
                    await btn.first.click(timeout=2500); await page.wait_for_timeout(90)
                except: break
            rows=page.locator('table tr')
            for i in range(await rows.count()):
                cells=rows.nth(i).locator('td'); n=await cells.count()
                if n<10: continue
                t=[' '.join((await cells.nth(j).inner_text()).split()) for j in range(n)]
                if 'минск-мир' not in t[0].lower() and 'минск мир' not in t[0].lower(): continue
                building=t[1]; unit=t[2]; floor=_int(t[3]); area=_num(t[4])
                if floor is None or area is None: continue
                def eur(cell):
                    vals=re.findall(r'([\d\s]+(?:[.,]\d+)?)\s*€',cell)
                    return _num(vals[-1]) if vals else None
                regular=eur(t[7]) if n>7 else None; fast=eur(t[9]) if n>9 else None
                key=make_key(building,unit,floor,area)
                old=found.get(key)
                if old:
                    if old.price_regular_eur is None: old.price_regular_eur=regular
                    if old.price_fast_eur is None: old.price_fast_eur=fast
                else:
                    found[key]=BirListing(key,building,None,unit,regular,fast,area,None,floor,{'cells':t})
            await b.close()
        return list(found.values())
