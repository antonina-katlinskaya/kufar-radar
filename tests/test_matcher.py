from radar.models import KufarListing,BirListing
from radar.matcher import match_new,mismatch_map

def b(key='x',area=30.41,price=43669,rooms=1,floor=2,address='Игоря Лученка, 22'):
    return BirListing(key,'Mediterranean',address,'239',50177,price,area,rooms,floor,{})

def k(**kw):
    x=dict(ad_id='1085587936',url='x',profile_id='11093294',price_eur=43669,area=30.40,rooms=1,floor=2,address='Лученка 22')
    x.update(kw); return KufarListing(**x)

def test_area_close_identifies_but_reports_exact_difference():
    r=match_new(k(),[b()]); assert r.obj is not None; assert r.confidence in {'EXACT','HIGH'}; assert 'area' in r.mismatches

def test_room_change_is_mismatch():
    r=match_new(k(area=30.41,rooms=2),[b()]); assert r.obj; assert r.mismatches['rooms']==(2,1)

def test_ambiguous_does_not_accuse():
    r=match_new(k(area=30.41),[b('a'),b('b')]); assert r.obj is None; assert r.confidence=='AMBIGUOUS'
