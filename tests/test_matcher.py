from radar.models import KufarListing,BirListing
from radar.matcher import area_close,match_new,mismatch_map,round_area_1

def b(key='x',area=30.41,price=43669,rooms=1,floor=2,address='Игоря Лученка, 22'):
    return BirListing(key,'Mediterranean',address,'239',50177,price,area,rooms,floor,{})

def k(**kw):
    x=dict(ad_id='1085587936',url='x',profile_id='11093294',price_eur=43669,area=30.40,rooms=1,floor=2,address='Лученка 22')
    x.update(kw); return KufarListing(**x)

def test_area_standard_rounding_is_not_a_mismatch():
    for bir_area,kufar_area in [(29.59,29.6),(31.08,31.1),(29.57,29.6),(29.71,29.7),(30.15,30.2),(8.31,8.3)]:
        r=match_new(k(area=kufar_area),[b(area=bir_area)])
        assert r.obj is not None
        assert 'area' not in r.mismatches

def test_area_that_rounds_to_another_tenth_remains_mismatch():
    r=match_new(k(area=8.3),[b(area=8.39)])
    assert r.obj is not None
    assert r.mismatches['area']==(8.3,8.39)

def test_half_rounds_up_not_bankers():
    assert str(round_area_1(30.15))=='30.2'
    assert area_close(30.2,30.15)

def test_room_change_is_mismatch():
    r=match_new(k(area=30.41,rooms=2),[b()]); assert r.obj; assert r.mismatches['rooms']==(2,1)

def test_ambiguous_does_not_accuse():
    r=match_new(k(area=30.41),[b('a'),b('b')]); assert r.obj is None; assert r.confidence=='AMBIGUOUS'
