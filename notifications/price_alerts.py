"""Send new Kufar/Bir price discrepancies through the existing Kufar Radar bot."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from radar.d1 import D1
from radar.telegram import Telegram


NEW_DB_ID = 'd8dd0219-8070-4f48-980d-312eba26209e'
MINSK = ZoneInfo('Europe/Minsk')


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
    return fallback or 'контакт не указан'


def format_alert(row):
    bir, kufar = whole(row['bir_quick_eur']), whole(row['kufar_eur'])
    return '\n'.join([
        '🚨 Цена на Куфаре ниже Bir',
        f"Конкурент: {contact(row['raw_json'], row['profile_id'])}",
        f"{row['bir_house']}, помещение № {row['unit_number'] or 'не указан'} · {row['kufar_area'] or '?'} м²",
        f'Bir, быстрая оплата: {euros(bir)} → Куфар: {euros(kufar)}',
        f'Ниже на {euros(bir-kufar)}',
        f"Размещено: {local_time(row['list_time'])}",
        f"Проверено: {local_time(row['kufar_checked_at'])}",
        f"Куфар: https://re.kufar.by/vi/{row['ad_id']}",
        f"Bir: https://bir.by/object/{row['bir_id']}/",
        'Сопоставление квартиры предварительное.',
    ])


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
        SELECT s.ad_id,s.profile_id,s.bir_id,s.bir_house,s.unit_number,s.kufar_area,
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

    pending = db.query("SELECT id,message FROM kufar_price_alert_queue WHERE status='pending' ORDER BY id LIMIT 10")
    telegram = Telegram() if pending else None
    sent = 0
    for item in pending:
        response = telegram.send(chat, item['message'])
        if not response.get('ok'):
            raise RuntimeError('Старый Telegram бот не подтвердил доставку')
        db.execute("UPDATE kufar_price_alert_queue SET status='sent',sent_at=datetime('now'),attempts=attempts+1,error=NULL WHERE id=?", [item['id']])
        sent += 1
    print(f'Checked {len(rows)} current matches; queued {queued}; sent {sent}; pending {max(0,len(pending)-sent)}')


if __name__ == '__main__':
    main()
