import json
from datetime import datetime, timezone

import pytest

from radar.matcher import inventory_first_match
from radar.models import KufarListing
from radar.source_snapshot import current_bir_special_price, load_bir_snapshot


def price_cell(eur, *, green=False, per_metre=False):
    color = 'style="color: #007952; font-weight: 600;" ' if green else ''
    more = ' columnMobHidden' if per_metre else ''
    return (
        f'<td {color}class="table-search__item item__price flat{more}">'
        f'<p>224 280 BYN</p><span class="tprice">{eur} €</span></td>'
    )


def sample_bir_html(*, discounted='66 540', extra_stage=False):
    regular = price_cell('76 911')
    promotion_per_metre = price_cell('1 341', green=True, per_metre=True)
    promotion_total = price_cell(discounted, green=True)
    middle = (
        price_cell('73 934') + price_cell('1 490', per_metre=True)
        if extra_stage else ''
    )
    return (
        '<tr data-loadobject="test-object">'
        '<td>Акция 2026 584</td><td>Дом 24.2.2</td>'
        '<td>49.62</td>'
        + regular + middle + promotion_per_metre + promotion_total + '</tr>'
    )


def test_current_promo_price_is_total_eur_not_old_detail_or_eur_per_square_metre():
    html = sample_bir_html()
    assert current_bir_special_price({'raw_html': html}) == 66540.0


def test_special_price_from_six_price_columns_uses_final_green_total():
    html = sample_bir_html(extra_stage=True)
    assert current_bir_special_price({'raw_html': html}) == 66540.0


def test_normal_current_price_is_read_from_table():
    assert current_bir_special_price(
        {'raw_html': sample_bir_html(discounted='69 220')}
    ) == 69220.0


def test_unrecognized_or_ambiguous_special_price_fails_closed():
    with pytest.raises(RuntimeError, match='Cannot verify current BIR special EUR price'):
        current_bir_special_price({'raw_html': '<tr><td>no special price</td></tr>'})
    with pytest.raises(RuntimeError, match='found 2'):
        current_bir_special_price(
            {'raw_html': sample_bir_html() + sample_bir_html()}
        )


class FakeHistoryDB:
    def query(self, sql, params=None):
        if 'FROM bir_scans' in sql:
            return [{
                'checked_at': datetime.now(timezone.utc).isoformat(),
                'parsed_count': 1277,
            }]
        if 'FROM bir_objects' in sql:
            listing = {
                'number': '584', 'area': '49.62', 'rooms': '1',
                'raw_html': sample_bir_html(),
            }
            detail = {
                'nomerPomeschenia': '584', 'obschPloschad': 49.62,
                'comnat': 1, 'etaj': 8,
                'Rassrochka10_cena': 69220, 'cena': 76911,
            }
            return [{
                'id': 'bir-test-584', 'house': 'Дом 24.2.2',
                'listing_json': json.dumps(listing, ensure_ascii=False),
                'detail_json': json.dumps(detail, ensure_ascii=False),
                'detail_fetched_at': '2026-09-28T02:00:53Z',
            }]
        raise AssertionError(sql)


def test_radar_accepts_barashenko_tuple_despite_stale_bir_detail_price():
    items, checked_at = load_bir_snapshot(FakeHistoryDB())
    assert checked_at
    assert len(items) == 1
    assert items[0].price_fast_eur == 66540
    assert items[0].raw['detail_special_price_eur'] == 69220
    k = KufarListing(
        ad_id='1092938824', url='https://re.kufar.by/vi/1092938824',
        profile_id='11077002', price_eur=66540, area=49.6, rooms=1,
        floor=12, address='площадь Старый Аэропорт, 2, Минск',
    )
    assert inventory_first_match(k, items) is items[0]
