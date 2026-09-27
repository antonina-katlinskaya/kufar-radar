"""Send new Kufar/Bir price discrepancies through the existing Kufar Radar bot."""
import json
from html import escape
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from radar.d1 import D1
from radar.telegram import Telegram


NEW_DB_ID = 'd8dd0219-8070-4f48-980d-312eba26209e'
MINSK = ZoneInfo('Europe/Minsk')
HOUSE_NAMES = {
    '4.2': 'Эверест', '11.1': 'Каспиан', '11.2': 'Медитерранеан',
    '21.1': 'Континенталь', '22.7': 'София',
    '24.2.1': 'Лира', '24.2.2': 'Орион', '24.2.3': 'Андромеда',
    '24.2.4': 'Сириус', '24.2.5': 'Вега',
    '27.5': 'Калемегдан', '27.6': 'Сад Эрмитаж', '27.11.1': 'Штадт Парк',
}


def whole(value):
    from decimal import Decimal, ROUND_HALF_UP
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def euros(value):
    return f'{whole(value):,}'.replace(',', ' ') + ' €'


def local_time(value):
    if not value:
        return 'не указано'
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(MINSK).strftime('%d.%m.%Y %H:%M')


def contact(raw, fallback):
    data = json.loads(raw or '{}')
    params = data.get('account_parameters') or []
    for key in ('contact_person', 'name'):
        for item in params:
            if item.get('p') == key and item.get('v'):
                return str(item['v'])
    return fallback if fallback and not fallback.startswith('account:') else 'контакт не указан'


def format_alert(row):
    bir, kufar = whole(row['bir_quick_eur']), whole(row['kufar_eur'])
    house = row['bir_house'] or 'Дом не указан'
    house_number = house.removeprefix('Дом ').strip()
    house_label = (HOUSE_NAMES.get(house_number, '') + ' · ' if house_number in HOUSE_NAMES else '') + house.lower().replace('дом ', 'дом ', 1)
    details = [f"Помещение № {row['unit_number'] or 'не указано'}"]
    if row.get('kufar_rooms') is not None:
        details.append(f"{row['kufar_rooms']}-комн.")
    if row.get('kufar_area') is not None:
        details.append(f"{str(row['kufar_area']).replace('.', ',')} м²")
    if row.get('kufar_floor') is not None:
        details.append(f"{row['kufar_floor']} этаж")
    return '\n'.join([
        '🟠 <b>ВЕРОЯТНО: ЦЕНА НА КУФАРЕ НИЖЕ Bir.by</b>',
        '',
        f"👤 <b>{escape(contact(row['raw_json'], row['profile_id']))}</b>",
        f"🏢 <b>{escape(house_label)}</b>",
        f"📍 {escape(row.get('kufar_address') or 'адрес не указан')}",
        f"🚪 {escape(' · '.join(details))}",
        '',
        f'<b>Куфар: {euros(kufar)}</b>',
        f'<b>Bir.by: {euros(bir)}</b>',
        f'Ниже на {euros(bir-kufar)}',
        '',
        f"🕒 Размещено {local_time(row['list_time'])} · Куфар проверен {local_time(row['kufar_checked_at'])} · Bir.by {local_time(row['bir_checked_at'])}",
    ])


def buttons(ad_id, bir_id):
    return [[
        {'text': 'Открыть Куфар', 'url': f'https://re.kufar.by/vi/{ad_id}'},
        {'text': 'Открыть Bir.by', 'url': f'https://bir.by/object/{bir_id}/'},
    ]]


def new_database():
    db = D1()
    db.url = db.url.rsplit('/', 2)[0] + '/' + NEW_DB_ID + '/query'
    return db


def main():
    owner_db = D1()
    chat = owner_db.get_state('telegram_chat_id')
    if not chat:
        raise RuntimeError('Личный чат старого бота не найден')
    db = new_database()
    run_started = datetime.now(timezone.utc).isoformat()
    state_rows = db.query("SELECT value FROM service_state WHERE key='price_alerts_last_checked' LIMIT 1")
    since = state_rows[0]['value'] if state_rows else '1970-01-01T00:00:00+00:00'
    rows = db.query("""
        WITH changed_ids AS (
            SELECT ad_id
            FROM kufar_bridge_events INDEXED BY kufar_bridge_events_time_ad
            WHERE observed_at > ?
            UNION ALL
            SELECT p.ad_id
            FROM bir_events e INDEXED BY bir_events_time_object
            JOIN kufar_match_proposals p INDEXED BY kufar_proposals_bir
              ON p.proposed_bir_id=e.object_id
            WHERE e.observed_at > ?
            UNION ALL
            SELECT ad_id
            FROM kufar_match_proposals INDEXED BY kufar_proposals_computed_ad
            WHERE computed_at > ?
        ),
        c AS (
            SELECT DISTINCT ad_id FROM changed_ids
        )
        SELECT k.ad_id,k.profile_id,p.proposed_bir_id AS bir_id,b.house AS bir_house,
               json_extract(b.detail_json,'$.nomerPomeschenia') AS unit_number,
               k.area AS kufar_area,k.rooms AS kufar_rooms,k.floor AS kufar_floor,k.address AS kufar_address,
               k.price_eur AS kufar_eur,json_extract(b.detail_json,'$.Rassrochka10_cena') AS bir_quick_eur,
               k.observed_at AS kufar_checked_at,b.detail_fetched_at AS bir_checked_at,
               CASE
                 WHEN ROUND(k.price_eur,0)<ROUND(json_extract(b.detail_json,'$.Rassrochka10_cena'),0) THEN 'PRICE_REVIEW'
                 WHEN ROUND(k.price_eur,0)>ROUND(json_extract(b.detail_json,'$.Rassrochka10_cena'),0) THEN 'PRICE_HIGHER'
                 ELSE 'NO_PRICE_GAP'
               END AS review_status,
               k.list_time,k.raw_json,
               a.bir_id AS previous_bir_id,a.kufar_eur AS previous_kufar,
               a.bir_eur AS previous_bir,a.is_lower AS previous_lower
        FROM c
        CROSS JOIN kufar_match_proposals p
        CROSS JOIN kufar_ads_live k
        CROSS JOIN bir_objects b
        LEFT JOIN kufar_reference_snapshot r ON r.ad_id=c.ad_id
        LEFT JOIN kufar_price_alert_state a ON a.ad_id=c.ad_id
        WHERE p.ad_id=c.ad_id AND p.level='ADDRESS_UNIQUE'
          AND k.ad_id=c.ad_id AND k.present=1 AND k.price_eur>0
          AND b.id=p.proposed_bir_id AND b.present=1
          AND (r.bir_id IS NULL OR r.bir_id=p.proposed_bir_id)
          AND json_extract(b.detail_json,'$.Rassrochka10_cena')>0
          AND json_extract(b.detail_json,'$.status')='Свободен'
          AND julianday('now')-julianday(k.observed_at)<2.0/24
          AND julianday('now')-julianday(b.detail_fetched_at)<1.0
    """, [since, since, since])
    queued = 0
    for row in rows:
        k, b = whole(row['kufar_eur']), whole(row['bir_quick_eur'])
        lower = int(k < b)
        prior = row['previous_bir_id']
        if prior == row['bir_id'] and row['previous_kufar'] == k and row['previous_bir'] == b and row['previous_lower'] == lower:
            continue
        statements = []
        if lower and row['review_status'] == 'PRICE_REVIEW':
            statements.append((
                "INSERT INTO kufar_price_alert_queue(ad_id,bir_id,kufar_eur,bir_eur,message,created_at,status) VALUES(?,?,?,?,?,datetime('now'),'pending')",
                [row['ad_id'], row['bir_id'], k, b, format_alert(row)],
            ))
            queued += 1
        statements.append((
            "INSERT INTO kufar_price_alert_state(ad_id,bir_id,kufar_eur,bir_eur,is_lower,updated_at) VALUES(?,?,?,?,?,datetime('now')) ON CONFLICT(ad_id) DO UPDATE SET bir_id=excluded.bir_id,kufar_eur=excluded.kufar_eur,bir_eur=excluded.bir_eur,is_lower=excluded.is_lower,updated_at=excluded.updated_at",
            [row['ad_id'], row['bir_id'], k, b, lower],
        ))
        db.batch(statements)

    pending = db.query("SELECT id,message,ad_id,bir_id FROM kufar_price_alert_queue WHERE status='pending' ORDER BY id LIMIT 10")
    telegram = Telegram() if pending else None
    sent = 0
    for item in pending:
        response = telegram.send(chat, item['message'], keyboard=buttons(item['ad_id'], item['bir_id']), parse_mode='HTML')
        if not response.get('ok'):
            raise RuntimeError('Старый Telegram бот не подтвердил доставку')
        db.execute("UPDATE kufar_price_alert_queue SET status='sent',sent_at=datetime('now'),attempts=attempts+1,error=NULL WHERE id=?", [item['id']])
        sent += 1
    db.execute(
        "INSERT INTO service_state(key,value,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
        ['price_alerts_last_checked', run_started, run_started],
    )
    print(f'Checked {len(rows)} changed matches; queued {queued}; sent {sent}; pending {max(0,len(pending)-sent)}')


if __name__ == '__main__':
    main()
