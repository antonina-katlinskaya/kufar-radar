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
