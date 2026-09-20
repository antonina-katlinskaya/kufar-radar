import re, hashlib
from urllib.parse import urlencode
from playwright.async_api import async_playwright
from ..config import settings
from ..models import BirListing

ROOM_FILTERS = [('1-room',1),('2-room',2),('3-room',3),('4-room',4),('5-room',5)]

def _num(v):
    if v is None: return None
    if isinstance(v,(int,float)): return float(v)
    s=str(v).replace('\xa0','').replace(' ','').replace(',','.')
    m=re.search(r'-?\d+(?:\.\d+)?',s)
    return float(m.group()) if m else None

def _int(v):
    n=_num(v); return int(n) if n is not None else None

def _eur_from_dual(cell):
    nums=re.findall(r'\d+', (cell or '').replace('\xa0',' '))
    if not nums: return None
    candidates=[]
    for i in range(1,len(nums)):
        left=int(''.join(nums[:i])); right=int(''.join(nums[i:]))
        if right<=0: continue
        ratio=left/right
        if 2.0 <= ratio <= 5.0:
            candidates.append((abs(ratio-3.45), right))
    if candidates:
        candidates.sort()
        return float(candidates[0][1])
    return None

def make_key(building,unit,floor,area):
    return hashlib.sha1(f'{building or ""}|{unit or ""}|{floor or ""}|{area or ""}'.encode()).hexdigest()

async def _parse_html(page, html, rooms):
    rows = await page.evaluate(r"""html => {
      const table = document.createElement('table');
      const tbody = document.createElement('tbody');
      table.appendChild(tbody);
      tbody.innerHTML = html;
      return Array.from(tbody.querySelectorAll('tr')).map(tr => ({
        cells: Array.from(tr.querySelectorAll('td')).map(td => td.innerText.replace(/\s+/g,' ').trim()),
        html: tr.outerHTML
      }));
    }""", html)
    out=[]
    for r in rows:
        t=r['cells']
        if len(t)<10: continue
        label=(t[0] or '').lower()
        if 'минск-мир' not in label and 'минск мир' not in label: continue
        building=t[1]; unit=t[2]; floor=_int(t[3]); area=_num(t[4])
        if floor is None or area is None: continue
        regular=_eur_from_dual(t[7]) if len(t)>7 else None
        fast=_eur_from_dual(t[9]) if len(t)>9 else None
        key=make_key(building,unit,floor,area)
        out.append(BirListing(key,building,None,unit,regular,fast,area,rooms,floor,{'cells':t,'row_html':r['html']}))
    return out

class BirCollector:
    def __init__(self): self.diagnostics=[]
    async def collect(self):
        found={}
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=settings.headless)
            ctx=await browser.new_context(locale='ru-RU', user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36')
            page=await ctx.new_page()
            await page.goto(settings.bir_search_url, wait_until='domcontentloaded', timeout=90000)
            endpoint='https://bir.by/ajax/get-search-objects-new/'
            for room_filter,room_count in ROOM_FILTERS:
                form=[
                  ('type','live'),('object[]','Minsk World'),('comnat[]',room_filter),
                  ('cenaOt',''),('cenaZaKvOt',''),('obschPloschadOt',''),
                  ('orderby','cena'),('ascdesc','ASC'),('limit','5000')
                ]
                body=urlencode(form)
                resp=await ctx.request.post(endpoint,headers={'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest','Referer':settings.bir_search_url},data=body)
                text=await resp.text()
                self.diagnostics.append((endpoint,'POST',resp.status,resp.headers.get('content-type',''),f'room={room_filter};len={len(text)}'))
                for x in await _parse_html(page,text,room_count):
                    found[x.object_key]=x
            # Catch any listings not classified by rooms.
            form=[('type','live'),('object[]','Minsk World'),('cenaOt',''),('cenaZaKvOt',''),('obschPloschadOt',''),('orderby','cena'),('ascdesc','ASC'),('limit','5000')]
            body=urlencode(form)
            resp=await ctx.request.post(endpoint,headers={'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest','Referer':settings.bir_search_url},data=body)
            text=await resp.text()
            self.diagnostics.append((endpoint,'POST',resp.status,resp.headers.get('content-type',''),f'all;len={len(text)}'))
            for x in await _parse_html(page,text,None):
                old=found.get(x.object_key)
                if old is None: found[x.object_key]=x
                else:
                    if old.price_regular_eur is None: old.price_regular_eur=x.price_regular_eur
                    if old.price_fast_eur is None: old.price_fast_eur=x.price_fast_eur
            await browser.close()
        return list(found.values())
