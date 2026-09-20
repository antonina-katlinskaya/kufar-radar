import re, json, base64
from urllib.parse import urlparse, parse_qs, unquote
from typing import Any
from playwright.async_api import async_playwright
from ..config import settings
from ..models import KufarListing

MW_HINTS=('минск мир','minsk world','минск-мир')

def _num(v):
    if v is None: return None
    if isinstance(v,(int,float)): return float(v)
    s=str(v).replace('\xa0','').replace(' ','').replace(',','.')
    m=re.search(r'-?\d+(?:\.\d+)?',s)
    return float(m.group()) if m else None

def _param(ad, key):
    p=(ad.get('adParams') or {}).get(key) or {}
    v=p.get('v')
    if isinstance(v,list):
        return v[0] if v else None
    return v

def _account_param(ad,key):
    p=(ad.get('accountParams') or {}).get(key) or {}
    return p.get('v')

def _calculator_price(ad,currency):
    for row in ad.get('calculator') or []:
        if str(row.get('currency','')).upper()==currency.upper():
            try: return float(row.get('price'))/100.0
            except: return None
    return None

def parse_ad_dict(d:dict[str,Any], profile_id:str):
    # We only accept an actual ad object, not wrapper dictionaries that contain an ads[] list.
    if 'adId' not in d or not isinstance(d.get('adParams'),dict):
        return None
    aid=str(d.get('adId'))
    if not aid.isdigit() or len(aid)<8: return None
    url=d.get('adViewLink') or f'https://re.kufar.by/vi/{aid}'
    address=d.get('address') or _account_param(d,'address') or d.get('addressWithDistrict')
    title=d.get('title') or d.get('subject')
    return KufarListing(
      ad_id=aid,url=str(url),profile_id=profile_id,
      price_eur=_calculator_price(d,'EUR'),
      price_byn=_calculator_price(d,'BYN'),
      area=_num(_param(d,'size')),
      rooms=int(_num(_param(d,'rooms'))) if _num(_param(d,'rooms')) is not None else None,
      floor=int(_num(_param(d,'floor'))) if _num(_param(d,'floor')) is not None else None,
      address=str(address) if address else None,
      title=str(title) if title else None,
      raw=d)

def contact_person(item):
    return str(_account_param(item.raw,'contactPerson') or '').strip()

def is_scope(item:KufarListing):
    raw=json.dumps(item.raw,ensure_ascii=False).lower()
    district=str(((item.raw.get('adParams') or {}).get('reDistrict') or {}).get('vl') or '').lower()
    complex_name=str(((item.raw.get('adParams') or {}).get('newBuildingsApartmentComplex') or {}).get('vl') or '').lower()
    mw = any(h in district or h in complex_name or h in raw for h in MW_HINTS)
    person = contact_person(item).casefold() == settings.kufar_contact_person.casefold()
    return mw and person

def _cursor_payload(url):
    try:
        q=parse_qs(urlparse(url).query); c=q.get('cursor',[None])[0]
        if not c: return None
        return json.loads(base64.b64decode(unquote(c)).decode())
    except: return None

def _cursor_url(template, page_no):
    d=dict(template); d['p']=page_no
    token=base64.b64encode(json.dumps(d,separators=(',',':')).encode()).decode()
    from urllib.parse import quote
    return f'https://re.kufar.by/agency?userId={settings.kufar_profile_id}&cursor={quote(token)}'

def _walk(x):
    if isinstance(x,dict):
        yield x
        for v in x.values():
            yield from _walk(v)
    elif isinstance(x,list):
        for v in x: yield from _walk(v)

async def _page_ads(page):
    out={}
    if await page.locator('script#__NEXT_DATA__').count():
        data=json.loads(await page.locator('script#__NEXT_DATA__').text_content())
        for d in _walk(data):
            x=parse_ad_dict(d,settings.kufar_profile_id)
            if x: out[x.ad_id]=x
    return out

class KufarCollector:
    def __init__(self): self.diagnostics=[]
    async def collect(self,max_pages=100):
        found={}
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=settings.headless)
            ctx=await browser.new_context(locale='ru-RU', user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36')
            page=await ctx.new_page()

            # First page: public profile URL.
            resp=await page.goto(settings.kufar_profile_url,wait_until='domcontentloaded',timeout=90000)
            await page.wait_for_timeout(350)
            batch=await _page_ads(page); found.update(batch)
            self.diagnostics.append((settings.kufar_profile_url,'GET',resp.status if resp else None,(resp.headers.get('content-type','') if resp else ''),f'page=1;ads={len(batch)};total={len(found)}'))

            links=await page.locator('a[href*="/agency?userId="][href*="cursor="]').evaluate_all('els=>els.map(e=>e.href)')
            templates=[_cursor_payload(h) for h in links]
            templates=[x for x in templates if x]
            template=templates[0] if templates else None

            if template:
                empty_streak=0
                for page_no in range(2,max_pages+1):
                    url=_cursor_url(template,page_no)
                    resp=await page.goto(url,wait_until='domcontentloaded',timeout=90000)
                    await page.wait_for_timeout(300)
                    batch=await _page_ads(page)
                    before=len(found); found.update(batch); added=len(found)-before
                    self.diagnostics.append((url,'GET',resp.status if resp else None,(resp.headers.get('content-type','') if resp else ''),f'page={page_no};ads={len(batch)};added={added};total={len(found)}'))
                    empty_streak = empty_streak + 1 if added==0 else 0
                    if empty_streak>=2: break

            result=[x for x in found.values() if is_scope(x)]
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
