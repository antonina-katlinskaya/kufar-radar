from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math
import re
from .house_directory import resolved_bir_address
from .models import KufarListing, BirListing

@dataclass
class MatchResult:
    obj: BirListing | None
    confidence: str
    reason: str
    mismatches: dict
    reference: BirListing | None = None

def norm_address(v: str | None) -> list[str]:
    if not v: return []
    s=v.lower().replace('ё','е')
    tokens=re.findall(r'[a-zа-я0-9]+',s)
    stop={
      'г','город','минск','ул','улица','дом','д','корпус','корп','проспект','пр',
      'площадь','пл','жилой','комплекс','жк','квартал',
    }
    return [t for t in tokens if t not in stop]

def address_equal(a,b):
    aa,bb=norm_address(a),norm_address(b)
    if not aa or not bb: return False
    na={x for x in aa if any(ch.isdigit() for ch in x)}
    nb={x for x in bb if any(ch.isdigit() for ch in x)}
    # Номер дома обязателен с обеих сторон. «Лученка» и «Лученка, 22» —
    # разные по качеству адреса и больше не считаются совпадением.
    if bool(na) != bool(nb): return False
    if na and not (na & nb): return False
    wa={x for x in aa if x not in na}; wb={x for x in bb if x not in nb}
    return bool(wa and wb and (wa<=wb or wb<=wa or len(wa&wb)>=max(1,min(len(wa),len(wb))-1)))

def round_area_1(v):
    if v is None: return None
    try:
        return Decimal(str(v)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None

def _decimal_area(v):
    if v is None: return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None

def area_close(kufar_area,bir_area):
    """Accept an exact value or Kufar's HALF_UP rounding of the BIR source value."""
    kufar=_decimal_area(kufar_area)
    bir=_decimal_area(bir_area)
    if kufar is None or bir is None:
        return False
    return kufar==bir or kufar==round_area_1(bir)

def price_matches(k,b,tol=1.0):
    if k is None: return False
    prices=[p for p in (b.price_fast_eur,b.price_regular_eur) if p is not None]
    return any(abs(k-p)<=tol for p in prices)

def _kufar_coords(k):
    rows=(k.raw or {}).get('ad_parameters')
    if isinstance(rows,list):
        for p in rows:
            if isinstance(p,dict) and p.get('p')=='coordinates':
                v=p.get('v')
                if isinstance(v,list) and len(v)>=2:
                    try: return float(v[1]),float(v[0])
                    except: return None
    if isinstance(rows,dict):
        p=rows.get('coordinates') or {}
        v=p.get('v') if isinstance(p,dict) else None
        if isinstance(v,list) and len(v)>=2:
            try: return float(v[1]),float(v[0])
            except: return None
    return None

def _bir_coords(b):
    v=(b.raw or {}).get('gps')
    if not v: return None
    try:
        a=[float(x.strip()) for x in str(v).split(',')]
        return (a[0],a[1]) if len(a)>=2 else None
    except: return None

def _distance_m(a,b):
    if not a or not b: return None
    lat1,lon1=a; lat2,lon2=b
    p1,p2=math.radians(lat1),math.radians(lat2)
    dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 6371000*2*math.asin(min(1,math.sqrt(h)))

def location_close(k,b,tol_m=250):
    d=_distance_m(_kufar_coords(k),_bir_coords(b))
    return None if d is None else d<=tol_m

def vector(k,b):
    official_address=resolved_bir_address(b)
    addr = None if not k.address or not official_address else address_equal(k.address,official_address)
    loc = None if official_address else location_close(k,b)
    return {
      'price': None if k.price_eur is None else price_matches(k.price_eur,b),
      'area': None if k.area is None or b.area is None else area_close(k.area,b.area),
      'rooms': None if k.rooms is None or b.rooms is None else k.rooms==b.rooms,
      'floor': None if k.floor is None or b.floor is None else k.floor==b.floor,
      'address': addr,
      'location': loc,
    }

def mismatch_map(k,b):
    out={}
    v=vector(k,b)
    if v['price'] is False: out['price']=(k.price_eur, {'fast':b.price_fast_eur,'regular':b.price_regular_eur})
    if v['area'] is False: out['area']=(k.area,b.area)
    if v['rooms'] is False: out['rooms']=(k.rooms,b.rooms)
    if v['floor'] is False: out['floor']=(k.floor,b.floor)
    if v['address'] is False: out['address']=(k.address,resolved_bir_address(b) or b.building_name)
    return out

def apply_mismatch_policy(k,b,mismatches):
    """Treat a verified floor-only difference as informational, not a violation."""
    out=dict(mismatches or {})
    if set(out) != {'floor'} or not b.unit_no:
        return out
    v=vector(k,b)
    required=('price','area','rooms','address')
    if all(v.get(field) is True for field in required):
        return {}
    return out

def match_new(k,candidates):
    scored=[]
    for b in candidates:
        v=vector(k,b); known=[x for x in v.values() if x is not None]
        if len(known)<3: continue
        mism=sum(x is False for x in known); matches=sum(x is True for x in known)
        scored.append((mism,-matches,b,v))
    scored.sort(key=lambda x:(x[0],x[1],x[2].object_key))
    if not scored: return MatchResult(None,'NONE','No sufficiently comparable Bir object',{})
    best=scored[0]
    mism,neg,b,v=best; known=sum(x is not None for x in v.values()); matches=-neg
    if mism==0 and matches>=3: conf='EXACT'
    elif mism==1 and known>=4 and matches>=3: conf='HIGH'
    elif mism<=2 and matches>=3: conf='MEDIUM'
    else: return MatchResult(None,'NONE',f'Best Bir candidate only matches {matches}/{known} comparable fields',{})
    tied=[x for x in scored if x[0]==best[0] and x[1]==best[1]]
    if len(tied)>1:
        reason=f'{len(tied)} Bir candidates tie at an otherwise acceptable score'
        addresses=[resolved_bir_address(x[2]) for x in tied]
        consensus=addresses[0] if addresses and all(addresses) else None
        if consensus and all(address_equal(consensus,address) for address in addresses[1:]):
            if not k.address or not address_equal(k.address,consensus):
                return MatchResult(None,'AMBIGUOUS',reason,{'address':(k.address,consensus)},tied[0][2])
        return MatchResult(None,'AMBIGUOUS',reason,{},tied[0][2])
    return MatchResult(b,conf,f'{matches}/{known} comparable fields match; {mism} disagree',mismatch_map(k,b))
