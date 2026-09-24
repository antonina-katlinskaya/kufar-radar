from radar.audit import AuditSession, listing_replaced
from radar.models import BirListing, KufarListing
import sqlite3


def bir(**kwargs):
    values=dict(
      object_key='bir-1',building_name='11.2',official_address='Игоря Лученка, 22',
      unit_no='8.43',price_regular_eur=47000,price_fast_eur=None,
      area=31.1,rooms=1,floor=8,raw={}
    )
    values.update(kwargs)
    return BirListing(**values)


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
    item.passport_confidence={}
    item.passport_updated_at={}
    item.recent_versions={}
    item.statements=[]
    item.active={}
    return item


def trust(item,object_key='bir-1',confidence='HIGH'):
    item.preferred['ad-1']=object_key
    item.passport_confidence['ad-1']=confidence
    item.passport_updated_at['ad-1']='2026-09-24T08:00:00+00:00'
    return item


def test_wrong_address_does_not_block_probable_price_violation():
    item=session()
    listing=kufar(price_eur=45000)
    result=item.audit(listing)
    assert result['status']=='PROBABLE'
    assert set(result['mismatches'])=={'price','address'}
    assert result['object_keys']['price']=='bir-1'
    events=item.sync(listing,result)
    assert {event['event_type'] for event in events}=={'PROBABLE_MISMATCH'}


def test_wrong_address_does_not_block_probable_area_violation():
    result=session().audit(kufar(area=31.8))
    assert result['status']=='PROBABLE'
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


def test_trusted_passport_catches_price_and_area_even_with_wrong_address():
    result=trust(session()).audit(kufar(price_eur=45000,area=31.8))
    assert result['status']=='MISMATCH'
    assert result['confidence']=='PASSPORT'
    assert {'price','area'} <= set(result['mismatches'])
    assert result['object_keys']['price']=='bir-1'
    assert result['object_keys']['area']=='bir-1'


def test_weak_match_is_not_treated_as_object_passport():
    result=trust(session(),confidence='FIELD_HIGH').audit(
      kufar(price_eur=45000,area=31.8)
    )
    assert result['status']=='INSUFFICIENT'
    assert result['mismatches']=={}


def test_two_core_changes_discard_old_passport_and_rematch_new_object():
    old=bir()
    new=bir(
      object_key='bir-2',building_name='12.1',official_address='Леонида Щемелёва, 30',
      unit_no='3.12',price_regular_eur=51000,area=36.2,rooms=2,floor=8
    )
    item=trust(session([old,new]))
    item.recent_versions['ad-1']=[
      {'observed_at':'2026-09-24T09:00:00+00:00','area':36.2,'rooms':2,'floor':8,'title':'Новая карточка','raw_json':'{}'},
      {'observed_at':'2026-09-24T07:00:00+00:00','area':31.1,'rooms':1,'floor':8,'title':'Старая карточка','raw_json':'{}'},
    ]
    result=item.audit(kufar(price_eur=51000,area=36.2,rooms=2))
    assert result['status']=='MISMATCH'  # only the deliberately wrong address remains internal
    assert 'price' not in result['mismatches'] and 'area' not in result['mismatches']
    assert result['object_key']=='bir-2'
    assert any(sql.startswith('DELETE FROM matches') for sql,_ in item.statements)


def test_two_independent_audits_detect_reuse_even_when_only_area_changed():
    old=bir()
    new=bir(
      object_key='bir-2',unit_no='8.44',price_regular_eur=51000,area=32.2
    )
    item=trust(session([old,new]))
    result=item.audit(kufar(price_eur=51000,area=32.2))
    assert result['object_key']=='bir-2'
    assert 'price' not in result['mismatches'] and 'area' not in result['mismatches']
    assert any(sql.startswith('DELETE FROM matches') for sql,_ in item.statements)


def test_title_and_image_support_replacement_when_one_core_field_changes():
    assert listing_replaced([
      {
        'area':36.2,'rooms':1,'floor':8,'title':'Другой дом',
        'raw_json':'{"primary_image_id":"new"}'
      },
      {
        'area':31.1,'rooms':1,'floor':8,'title':'Старый дом',
        'raw_json':'{"primary_image_id":"old"}'
      },
    ])


def test_address_price_and_title_edits_do_not_break_passport_by_themselves():
    assert not listing_replaced([
      {
        'area':31.1,'rooms':1,'floor':8,'title':'Новый заголовок',
        'raw_json':'{"primary_image_id":"new"}'
      },
      {
        'area':31.1,'rooms':1,'floor':8,'title':'Старый заголовок',
        'raw_json':'{"primary_image_id":"old"}'
      },
    ])


def test_passport_created_after_replacement_history_is_not_discarded_again():
    item=trust(session())
    item.passport_updated_at['ad-1']='2026-09-24T10:00:00+00:00'
    item.recent_versions['ad-1']=[
      {'observed_at':'2026-09-24T09:00:00+00:00','area':36.2,'rooms':2,'floor':8},
      {'observed_at':'2026-09-24T07:00:00+00:00','area':31.1,'rooms':1,'floor':8},
    ]
    assert not item.passport_predates_latest_version('ad-1')


def test_audit_session_loads_trusted_passport_and_two_latest_versions():
    connection=sqlite3.connect(':memory:')
    connection.row_factory=sqlite3.Row
    connection.executescript('''
      CREATE TABLE bir_objects (
        object_key TEXT, building_name TEXT, official_address TEXT, unit_no TEXT,
        active INTEGER, price_regular_eur REAL, price_fast_eur REAL, area REAL,
        rooms INTEGER, floor INTEGER, raw_json TEXT
      );
      CREATE TABLE events (
        id INTEGER, ad_id TEXT, field_name TEXT, active INTEGER, occurred_at TEXT
      );
      CREATE TABLE matches (
        ad_id TEXT, object_key TEXT, confidence TEXT, updated_at TEXT
      );
      CREATE TABLE kufar_versions (
        id INTEGER PRIMARY KEY, ad_id TEXT, observed_at TEXT, area REAL,
        rooms INTEGER, floor INTEGER, title TEXT, raw_json TEXT
      );
      INSERT INTO bir_objects VALUES (
        'bir-1','11.2','Игоря Лученка, 22','8.43',1,47000,NULL,31.1,1,8,'{}'
      );
      INSERT INTO matches VALUES (
        'ad-1','bir-1','HIGH','2026-09-24T10:00:00+00:00'
      );
      INSERT INTO kufar_versions VALUES
        (1,'ad-1','2026-09-24T07:00:00+00:00',31.1,1,8,'Первая','{}'),
        (2,'ad-1','2026-09-24T08:00:00+00:00',31.2,1,8,'Вторая','{}'),
        (3,'ad-1','2026-09-24T09:00:00+00:00',31.3,1,8,'Третья','{}');
    ''')

    class DB:
        def query(self,sql,params=None):
            rows=connection.execute(sql,params or []).fetchall()
            return [dict(row) for row in rows]

    item=AuditSession(DB(),['ad-1'])
    assert item.preferred['ad-1']=='bir-1'
    assert item.passport_confidence['ad-1']=='HIGH'
    assert [row['id'] for row in item.recent_versions['ad-1']]==[3,2]
