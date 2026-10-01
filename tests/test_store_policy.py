import json
from radar.models import KufarListing
from radar.store import kufar_change_relevant, price_change_relevant


def listing(**kwargs):
    values=dict(ad_id='1',url='x',profile_id='p',price_eur=30000,price_byn=100000,
                area=30.0,rooms=1,floor=2,address='Игоря Лученка, 22',title='Квартира',
                raw={'list_time':'2026-09-24T08:00:00Z'})
    values.update(kwargs)
    return KufarListing(**values)


def old_row(**kwargs):
    values=dict(active=1,price_eur=30000,price_byn=100000,area=30.0,rooms=1,floor=2,
                address='Игоря Лученка, 22',title='Квартира',
                raw_json='{"list_time":"2026-09-24T08:00:00Z"}')
    values.update(kwargs)
    return values


def test_euro_conversion_noise_is_not_a_real_listing_change_when_byn_is_stable():
    assert not price_change_relevant(old_row(),listing(price_eur=30100))
    assert not kufar_change_relevant(old_row(),listing(price_eur=30100))


def test_source_price_or_raise_time_change_is_audited():
    assert price_change_relevant(old_row(),listing(price_byn=100500))
    assert kufar_change_relevant(
        old_row(),listing(raw={'list_time':'2026-09-24T09:00:00Z'})
    )

def test_only_price_area_rooms_or_raise_trigger_audit():
    assert kufar_change_relevant(old_row(),listing(area=30.1))
    assert kufar_change_relevant(old_row(),listing(rooms=2))
    assert not kufar_change_relevant(old_row(),listing(floor=9))
    assert not kufar_change_relevant(old_row(),listing(address='Другой адрес'))
    assert not kufar_change_relevant(old_row(),listing(title='Другой заголовок'))


def test_exchange_rate_changes_are_ignored_when_original_currency_price_is_stable():
    raw={'currency':'USD','calculator':[{'currency':'USD','price':'3500000'}],
         'list_time':'2026-09-24T08:00:00Z'}
    old=old_row(price_byn=100000,raw_json='{"currency":"USD","calculator":[{"currency":"USD","price":"3500000"}],"list_time":"2026-09-24T08:00:00Z"}')
    assert not price_change_relevant(old,listing(price_eur=29900,price_byn=101000,raw=raw))
    changed_raw=dict(raw,calculator=[{'currency':'USD','price':'3600000'}])
    assert price_change_relevant(old,listing(raw=changed_raw))


class RecordingDB:
    def __init__(self, row):
        self.row = row
        self.writes = []

    def query(self, sql, params):
        return [self.row]

    def batch(self, statements):
        self.writes.extend(statements)


def test_save_kufar_does_not_write_when_only_exchange_rate_changes():
    from radar.store import save_kufar

    raw = {'currency': 'EUR', 'calculator': [{'currency': 'EUR', 'price': '3000000'}],
           'list_time': '2026-09-24T08:00:00Z'}
    db = RecordingDB(old_row(ad_id='1', fingerprint='old-fx-dependent',
                             raw_json=json.dumps(raw)))
    save_kufar(db, [listing(price_eur=30000, price_byn=101000, raw=raw)], 'p')
    assert db.writes == []


def test_save_kufar_records_native_price_change():
    from radar.store import save_kufar

    raw = {'currency': 'EUR', 'calculator': [{'currency': 'EUR', 'price': '3000000'}],
           'list_time': '2026-09-24T08:00:00Z'}
    db = RecordingDB(old_row(ad_id='1', fingerprint='old-fx-dependent',
                             raw_json=json.dumps(raw)))
    changed = dict(raw, calculator=[{'currency': 'EUR', 'price': '3100000'}])
    save_kufar(db, [listing(price_eur=31000, price_byn=104000, raw=changed)], 'p')
    assert len(db.writes) == 2
    assert any('kufar_versions' in sql for sql, _ in db.writes)
