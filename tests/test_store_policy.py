from radar.models import KufarListing
from radar.store import kufar_change_relevant, price_change_relevant, save_kufar


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


def test_source_price_or_publication_time_change_is_audited():
    assert price_change_relevant(old_row(),listing(price_byn=100500))
    assert kufar_change_relevant(
        old_row(),listing(raw={'list_time':'2026-09-24T09:00:00Z'})
    )


def test_exchange_rate_changes_are_ignored_when_original_currency_price_is_stable():
    raw={'currency':'USD','calculator':[{'currency':'USD','price':'3500000'}],
         'list_time':'2026-09-24T08:00:00Z'}
    old=old_row(price_byn=100000,raw_json='{"currency":"USD","calculator":[{"currency":"USD","price":"3500000"}],"list_time":"2026-09-24T08:00:00Z"}')
    assert not price_change_relevant(old,listing(price_eur=29900,price_byn=101000,raw=raw))
    changed_raw=dict(raw,calculator=[{'currency':'USD','price':'3600000'}])
    assert price_change_relevant(old,listing(raw=changed_raw))


def test_save_kufar_reuses_snapshot_for_previous_active_count():
    item=listing(price_byn=100500)
    existing=old_row(ad_id='1',profile_id='p',fingerprint='old',first_seen_at='2026-09-24T00:00:00Z')

    class SnapshotDB:
        def __init__(self):
            self.queries=[]
            self.batches=[]
        def query(self,sql,params):
            self.queries.append((sql,params))
            return [existing]
        def batch(self,statements):
            self.batches.extend(statements)

    db=SnapshotDB()
    changed,previous_active=save_kufar(db,[item],'p')
    assert previous_active==1
    assert changed==[item]
    assert len(db.queries)==1
    assert db.queries[0][0]=='SELECT * FROM kufar_ads WHERE profile_id=?'
