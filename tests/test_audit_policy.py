from radar.audit import AuditSession
from radar.models import BirListing, KufarListing


def bir():
    return BirListing(
      object_key='bir-1',building_name='11.2',official_address='Игоря Лученка, 22',
      unit_no='8.43',price_regular_eur=47000,price_fast_eur=None,
      area=31.1,rooms=1,floor=8,raw={}
    )


def kufar(**kwargs):
    values=dict(
      ad_id='ad-1',url='x',profile_id='11077002',price_eur=47000,
      area=31.1,rooms=1,floor=8,address='Братская ул, 1, Минск',
      title='Квартира в Минск-Мире',raw={}
    )
    values.update(kwargs)
    return KufarListing(**values)


def session(candidates=None):
    item=object.__new__(AuditSession)
    item.candidates=list(candidates or [bir()])
    item.inactive_candidates=[]
    item.preferred={}
    item.statements=[]
    item.active={}
    return item


def test_wrong_address_does_not_block_confirmed_price_violation():
    result=session().audit(kufar(price_eur=45000))
    assert result['status']=='MISMATCH'
    assert set(result['mismatches'])=={'price','address'}
    assert result['object_keys']['price']=='bir-1'


def test_wrong_address_does_not_block_confirmed_area_violation():
    result=session().audit(kufar(area=31.8))
    assert result['status']=='MISMATCH'
    assert set(result['mismatches'])=={'area','address'}
    assert result['object_keys']['area']=='bir-1'


def test_both_key_values_wrong_without_independent_identity_do_not_create_red_violation():
    listing=kufar(
      price_eur=45000,area=31.8,
      raw={'ad_parameters':[{'p':'re_district','vl':'Минск-Мир'}]}
    )
    result=session().audit(listing)
    assert result['status']=='INSUFFICIENT'
    assert result['mismatches']=={}
