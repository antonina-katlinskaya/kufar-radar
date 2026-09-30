from radar.d1 import D1
from radar.telegram import Telegram


def main():
    db=D1(); tg=Telegram()
    chat=db.get_state('telegram_chat_id')
    if not chat:
        raise RuntimeError('Telegram owner chat is not configured')

    rows=db.query(
      """SELECT e.field_name,e.event_type,e.occurred_at,e.new_value,e.bir_value,
                k.ad_id,k.profile_id,k.area,k.rooms,k.floor,k.price_eur,k.url
           FROM events e
           JOIN kufar_ads k ON k.ad_id=e.ad_id
          WHERE e.active=1 AND k.active=1
            AND e.field_name IN ('price','area')
          ORDER BY e.occurred_at DESC
          LIMIT 10"""
    )

    counts=db.query(
      """SELECT e.field_name,COUNT(*) AS n
           FROM events e
           JOIN kufar_ads k ON k.ad_id=e.ad_id
          WHERE e.active=1 AND k.active=1
            AND e.field_name IN ('price','area')
          GROUP BY e.field_name
          ORDER BY e.field_name"""
    )
    count_map={str(r['field_name']):int(r['n']) for r in counts}

    parts=[
      '🧪 ТЕСТ РАДАРА — только владельцу',
      '',
      'Telegram-канал связи работает: это сообщение отправлено напрямую владельцу из GitHub Actions.',
      '',
      f"Активные сигналы сейчас: цена — {count_map.get('price',0)}, площадь — {count_map.get('area',0)}.",
    ]

    if rows:
        parts += ['', 'Последние активные сигналы:']
        for r in rows:
            kind='Цена' if r['field_name']=='price' else 'Площадь'
            parts.append(
              f"• {kind} · объявление {r['ad_id']} · "
              f"{r.get('rooms') or '—'} комн. · {r.get('area') or '—'} м² · "
              f"{r.get('price_eur') or '—'} €\n{r.get('url') or ''}"
            )
    else:
        parts += ['', 'Активных сигналов цены/площади сейчас нет.']

    tg.send(chat,'\n'.join(parts))


if __name__=='__main__':
    main()
