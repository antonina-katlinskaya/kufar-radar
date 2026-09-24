import re
from urllib.parse import urlencode
from playwright.async_api import async_playwright
from ..config import settings
from ..house_directory import directory_address
from ..models import BirListing

ROOM_FILTERS=[('1-room',1),('2-room',2),('3-room',3),('4-room',4),('5-room',5)]

def _num(v):
    if v is None: return None
    if isinstance(v,(int,float)): return float(v)
    s=str(v).replace('\xa0','').replace(' ','').replace(',','.')
    m=re.search(r'-?\d+(?:\.\d+)?',s)
    return float(m.group()) if m else None

def _int(v):
    n=_num(v); return int(n) if n is not None else None

async def _parse_html(page, html, rooms):
    rows=await page.evaluate(r"""html => {
      const table=document.createElement('table');
      const tbody=document.createElement('tbody');
      table.appendChild(tbody);
      tbody.innerHTML=html;
      return Array.from(tbody.querySelectorAll('tr.loadobject')).map(tr=>{
        const tds=Array.from(tr.querySelectorAll('td'));
        const house=tr.querySelector('a.housename');
        const addr=house ? house.querySelector('span') : null;
        const directHouseText=house ? Array.from(house.childNodes)
          .filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join(' ').replace(/\s+/g,' ').trim() : '';
        const complex=tr.querySelector('a.complexName');
        return {
          object_id: tr.getAttribute('data-loadobject') || '',
          complex: complex ? complex.textContent.replace(/\s+/g,' ').trim() : '',
          building: directHouseText,
          address: addr ? addr.textContent.replace(/\s+/g,' ').trim() : '',
          house_href: house ? house.getAttribute('href') : '',
          cells: tds.map(td=>td.innerText.replace(/\s+/g,' ').trim()),
          regular_eur: tds[7] ? (tds[7].querySelector('.tprice')?.textContent || '') : '',
          fast_eur: tds[9] ? (tds[9].querySelector('.tprice')?.textContent || '') : ''
        };
      });
    }""",html)
    out=[]
    for r in rows:
        t=r['cells']
        if len(t)<10: continue
        if 'минск-мир' not in (r.get('complex') or '').lower() and 'минск мир' not in (r.get('complex') or '').lower(): continue
        unit=t[2]; floor=_int(t[3]); area=_num(t[4])
        if floor is None or area is None: continue
        object_key=r.get('object_id') or f"{r.get('building')}|{unit}|{floor}|{area}"
        official_address=(r.get('address') or None) or directory_address(
          r.get('building'),r.get('house_href')
        )
        out.append(BirListing(
          object_key=object_key,
          building_name=(r.get('building') or None),
          official_address=official_address,
          unit_no=str(unit),
          price_regular_eur=_num(r.get('regular_eur')),
          price_fast_eur=_num(r.get('fast_eur')),
          area=area,rooms=rooms,floor=floor,
          raw={'cells':t,'house_href':r.get('house_href'),'complex':r.get('complex')}
        ))
    return out

class BirCollector:
    def __init__(self): self.diagnostics=[]
    async def collect(self):
        found={}
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=settings.headless)
            ctx=await browser.new_context(locale='ru-RU',user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36')
            page=await ctx.new_page()
            await page.goto(settings.bir_search_url,wait_until='domcontentloaded',timeout=90000)
            endpoint='https://bir.by/ajax/get-search-objects-new/'
            for room_filter,room_count in ROOM_FILTERS:
                form=[('type','live'),('object[]','Minsk World'),('comnat[]',room_filter),('cenaOt',''),('cenaZaKvOt',''),('obschPloschadOt',''),('orderby','cena'),('ascdesc','ASC'),('limit','5000')]
                resp=await ctx.request.post(endpoint,headers={'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest','Referer':settings.bir_search_url},data=urlencode(form))
                text=await resp.text()
                self.diagnostics.append((endpoint,'POST',resp.status,resp.headers.get('content-type',''),f'room={room_filter};len={len(text)}'))
                for x in await _parse_html(page,text,room_count):
                    found[x.object_key]=x

            # New Minsk World buildings often have an empty text address in Bir, but the
            # object-detail endpoint provides a stable building GPS point. One detail request
            # per building is enough; attach that GPS to every unit in the same building.
            detail_endpoint='https://bir.by/ajax/get-object-by-tablerow-click/'
            reps={}
            for x in found.values():
                if x.building_name and x.building_name not in reps:
                    reps[x.building_name]=x
            gps_by_building={}
            for building,x in reps.items():
                try:
                    resp=await ctx.request.post(
                        detail_endpoint,
                        headers={'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest','Referer':settings.bir_search_url},
                        data=urlencode({'objectid':x.object_key})
                    )
                    d=await resp.json()
                    gps=str(d.get('gps') or '').strip()
                    if gps:
                        gps_by_building[building]=gps
                except Exception:
                    continue
            for x in found.values():
                gps=gps_by_building.get(x.building_name)
                if gps:
                    x.raw['gps']=gps
            self.diagnostics.append((detail_endpoint,'POST',200,'application/json',f'building_gps={len(gps_by_building)}/{len(reps)}'))
            await browser.close()
        return list(found.values())
