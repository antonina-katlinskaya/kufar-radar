import re, json
from typing import Any
import httpx
from playwright.async_api import async_playwright
from ..config import settings
from ..models import KufarListing

API_URL='https://cre-api.kufar.by/ads-search/v1/engine/v2/search/rendered-paginated'
MW_HINTS=('минск мир','minsk world','минск-мир')

def _num(v):
    if v is None: return None
    if isinstance(v,(int,float)): return float(v)
    s=str(v).replace('\xa0','').replace(' ','').replace(',','.')
    m=re.search(r'-?\d+(?:\.\d+)?',s)
    return float(m.group()) if m else None

def _list_param(rows,key):
    for p in rows or []:
        if isinstance(p,dict) and p.get('p')==key:
            v=p.get('v')
            if isinstance(v,list): return v[0] if v else None
            return v
    return None

def _list_label(rows,key):
    for p in rows or []:
        if isinstance(p,dict) and p.get('p')==key:
            v=p.get('vl')
            if isinstance(v,list): return v[0] if v else None
            return v
    return None

def _camel_param(ad,key):
    p=(ad.get('adParams') or {}).get(key) or {}
    v=p.get('v')
    if isinstance(v,list): return v[0] if v else None
    return v

def _account_param(ad,key):
    ap=ad.get('account_parameters')
    if isinstance(ap,list):
        return _list_param(ap,key)
    if isinstance(ap,dict):
        p=ap.get(key) or {}
        if isinstance(p,dict): return p.get('v')
        return p
    p=(ad.get('accountParams') or {}).get(key) or {}
    return p.get('v') if isinstance(p,dict) else p

def _ad_param(ad,key):
    if isinstance(ad.get('ad_parameters'),list):
        return _list_param(ad.get('ad_parameters'),key)
    return _camel_param(ad,key)

def _calculator_price(ad,currency):
    for row in ad.get('calculator') or []:
        if str(row.get('currency','')).upper()==currency.upper():
            try: return float(row.get('price'))/100.0
            except: return None
    return None

def _primary_image_id(ad):
    image=ad.get('image') or ad.get('main_image') or ad.get('mainImage') or {}
    if isinstance(image,dict):
        value=image.get('image_id',image.get('imageId',image.get('id')))
        if value is not None: return str(value)
    images=ad.get('images') or []
    if isinstance(images,list) and images:
        first=images[0]
        if isinstance(first,dict):
            value=first.get('image_id',first.get('imageId',first.get('id')))
            if value is not None: return str(value)
    return None

def parse_ad_dict(d:dict[str,Any], profile_id:str):
    aid=d.get('ad_id',d.get('adId'))
    if aid is None: return None
    aid=str(aid)
    if not aid.isdigit() or len(aid)<8: return None
    url=d.get('ad_link') or d.get('adViewLink') or f'https://re.kufar.by/vi/{aid}'
    address=_account_param(d,'address') or d.get('address') or d.get('addressWithDistrict')
    title=d.get('subject') or d.get('title')
    rooms=_num(_ad_param(d,'rooms')); floor=_num(_ad_param(d,'floor'))
    compact_raw={
      'ad_id':d.get('ad_id',d.get('adId')),
      'ad_link':url,
      'list_time':d.get('list_time',d.get('date')),
      'subject':title,
      'primary_image_id':_primary_image_id(d),
      'currency':d.get('currency'),
      'price_byn':d.get('price_byn'),
      'calculator':d.get('calculator') or [],
      'ad_parameters':d.get('ad_parameters') or d.get('adParams') or {},
      'account_parameters':d.get('account_parameters') or d.get('accountParams') or {},
    }
    return KufarListing(
      ad_id=aid,url=str(url),profile_id=profile_id,
      price_eur=_calculator_price(d,'EUR'),
      price_byn=_calculator_price(d,'BYN') or (_num(d.get('price_byn'))/100.0 if d.get('price_byn') else None),
      area=_num(_ad_param(d,'size')),
      rooms=int(rooms) if rooms is not None else None,
      floor=int(floor) if floor is not None else None,
      address=str(address) if address else None,
      title=str(title) if title else None,
      raw=compact_raw)

def contact_person(item):
    return str(_account_param(item.raw,'contact_person') or _account_param(item.raw,'contactPerson') or '').strip()

def is_mw_claimed(item:KufarListing):
    if isinstance(item.raw.get('ad_parameters'),list):
        district=str(_list_label(item.raw.get('ad_parameters'),'re_district') or _ad_param(item.raw,'re_district') or '').lower()
        complex_name=str(_list_label(item.raw.get('ad_parameters'),'new_buildings_apartment_complex') or _ad_param(item.raw,'new_buildings_apartment_complex') or '').lower()
    else:
        district=str(((item.raw.get('adParams') or {}).get('reDistrict') or {}).get('vl') or _ad_param(item.raw,'re_district') or '').lower()
        complex_name=str(((item.raw.get('adParams') or {}).get('newBuildingsApartmentComplex') or {}).get('vl') or _ad_param(item.raw,'new_buildings_apartment_complex') or '').lower()
    raw=' '.join([district,complex_name,item.address or '',item.title or '']).lower()
    return any(h in raw for h in MW_HINTS)

class KufarCollector:
    def __init__(self,profile_id=None,contact_name=None):
        self.diagnostics=[]
        self.profile_id=str(profile_id or settings.kufar_profile_id)
        self.contact_name=settings.kufar_contact_person if contact_name is None and profile_id is None else contact_name
    async def collect(self,max_pages=100):
        params={'atid':self.profile_id,'lang':'ru','size':'45','typ':'sell','prn':'1000','sort':'lst.d'}
        found={}
        cursor=None
        api_total=0
        async with httpx.AsyncClient(timeout=60,follow_redirects=True,headers={'User-Agent':'Mozilla/5.0'}) as client:
            for page_no in range(1,max_pages+1):
                q=dict(params)
                if cursor: q['cursor']=cursor
                r=await client.get(API_URL,params=q)
                r.raise_for_status()
                data=r.json()
                api_total=data.get('total') or api_total
                ads=data.get('ads') or []
                for d in ads:
                    x=parse_ad_dict(d,self.profile_id)
                    if x: found[x.ad_id]=x
                self.diagnostics.append((str(r.url),'GET',r.status_code,r.headers.get('content-type',''),f'page={page_no};ads={len(ads)};total_seen={len(found)};api_total={data.get("total")}'))
                nxt=None
                for p in ((data.get('pagination') or {}).get('pages') or []):
                    if p.get('label')=='next' and p.get('token'):
                        nxt=p['token']; break
                if not nxt or not ads: break
                cursor=nxt

            # The newest-first feed can shift while it is being scanned. If rows are still
            # missing according to total, merge a few pages from the oldest side.
            if api_total and len(found)<api_total:
                oldest_params=dict(params); oldest_params['sort']='lst.a'
                cursor2=None
                try:
                    for page_no in range(1,8):
                        q=dict(oldest_params)
                        if cursor2: q['cursor']=cursor2
                        r=await client.get(API_URL,params=q)
                        r.raise_for_status()
                        data=r.json()
                        ads=data.get('ads') or []
                        for d in ads:
                            x=parse_ad_dict(d,self.profile_id)
                            if x: found[x.ad_id]=x
                        self.diagnostics.append((str(r.url),'GET',r.status_code,r.headers.get('content-type',''),f'oldest_pass={page_no};ads={len(ads)};total_seen={len(found)};api_total={data.get("total")}'))
                        if len(found)>=api_total: break
                        cursor2=None
                        for p in ((data.get('pagination') or {}).get('pages') or []):
                            if p.get('label')=='next' and p.get('token'):
                                cursor2=p['token']; break
                        if not cursor2 or not ads: break
                except Exception as e:
                    self.diagnostics.append(('oldest-pass','GET',None,'',f'ignored error: {e!r}'))

        items=list(found.values())
        if self.contact_name:
            expected=str(self.contact_name).casefold()
            items=[x for x in items if contact_person(x).casefold()==expected]
        return items

async def screenshot_ad(url,path):
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True); pg=await b.new_page(viewport={'width':1440,'height':1100})
        try:
            await pg.goto(url,wait_until='domcontentloaded',timeout=60000); await pg.wait_for_timeout(1200)
            await pg.screenshot(path=path,full_page=True)
            return True
        except: return False
        finally: await b.close()
