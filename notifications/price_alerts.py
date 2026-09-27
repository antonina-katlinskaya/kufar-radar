"""Send new Kufar/Bir price discrepancies through the existing Kufar Radar bot."""
import json
from html import escape
from datetime import datetime
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
    rows = db.query("""
        SELECT s.ad_id,s.profile_id,s.bir_id,s.bir_house,s.unit_number,s.kufar_area,s.kufar_rooms,s.kufar_floor,s.kufar_address,
               s.kufar_eur,s.bir_quick_eur,s.kufar_checked_at,s.bir_checked_at,
               s.review_status,k.list_time,k.raw_json,
               a.bir_id AS previous_bir_id,a.kufar_eur AS previous_kufar,
               a.bir_eur AS previous_bir,a.is_lower AS previous_lower
        FROM bir_kufar_strong_candidates s
        JOIN kufar_ads_live k ON k.ad_id=s.ad_id
        LEFT JOIN kufar_price_alert_state a ON a.ad_id=s.ad_id
        WHERE s.bir_id IS NOT NULL AND s.kufar_eur>0 AND s.bir_quick_eur>0
          AND s.bir_status='Свободен'
          AND julianday('now')-julianday(s.kufar_checked_at)<2.0/24
          AND julianday('now')-julianday(s.bir_checked_at)<1.0
          AND s.review_status IN ('PRICE_REVIEW','NO_PRICE_GAP','PRICE_HIGHER')
    """)
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
    print(f'Checked {len(rows)} current matches; queued {queued}; sent {sent}; pending {max(0,len(pending)-sent)}')


if __name__ == '__main__':
    main()
