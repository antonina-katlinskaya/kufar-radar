from dataclasses import dataclass
import re
from .models import KufarListing, BirListing

@dataclass
class MatchResult:
    obj: BirListing | None
    confidence: str
    reason: str
    mismatches: dict

def norm_address(v: str | None) -> list[str]:
    if not v: return []
    s=v.lower().replace('ё','е')
    tokens=re.findall(r'[a-zа-я0-9]+',s)
    stop={'г','город','минск','ул','улица','дом','д','корпус','корп','проспект','пр'}
    return [t for t in tokens if t not in stop]

def address_equal(a,b):
    aa,bb=norm_address(a),norm_address(b)
    if not aa or not bb: return False
    na={x for x in aa if x.isdigit()}; nb={x for x in bb if x.isdigit()}
    if na and nb and not (na & nb): return False
    wa={x for x in aa if not x.isdigit()}; wb={x for x in bb if not x.isdigit()}
    return bool(wa and wb and (wa<=wb or wb<=wa or len(wa&wb)>=max(1,min(len(wa),len(wb))-1)))

def area_close(a,b,tol=0.09):
    return a is not None and b is not None and abs(a-b)<=tol

def price_matches(k,b,tol=1.0):
    if k is None: return False
    prices=[p for p in (b.price_fast_eur,b.price_regular_eur) if p is not None]
    return any(abs(k-p)<=tol for p in prices)

def vector(k,b):
    return {
      'price': None if k.price_eur is None else price_matches(k.price_eur,b),
      'area': None if k.area is None or b.area is None else area_close(k.area,b.area),
      'rooms': None if k.rooms is None or b.rooms is None else k.rooms==b.rooms,
      'floor': None if k.floor is None or b.floor is None else k.floor==b.floor,
      'address': None if not k.address or not b.official_address else address_equal(k.address,b.official_address),
    }

def mismatch_map(k,b):
    out={}
    v=vector(k,b)
    if v['price'] is False: out['price']=(k.price_eur, {'fast':b.price_fast_eur,'regular':b.price_regular_eur})
    if k.area is not None and b.area is not None and abs(k.area-b.area)>1e-9: out['area']=(k.area,b.area)
    if v['rooms'] is False: out['rooms']=(k.rooms,b.rooms)
    if v['floor'] is False: out['floor']=(k.floor,b.floor)
    if v['address'] is False: out['address']=(k.address,b.official_address or b.building_name)
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
    if len(tied)>1: return MatchResult(None,'AMBIGUOUS',f'{len(tied)} Bir candidates tie at an otherwise acceptable score',{})
    return MatchResult(b,conf,f'{matches}/{known} comparable fields match; {mism} disagree',mismatch_map(k,b))
