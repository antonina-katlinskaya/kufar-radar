import json
from radar.d1 import D1
from radar.telegram import Telegram
from radar.models import KufarListing
from radar.main import fmt_event_group

def k_from_row(r):
    raw={}
    try: raw=json.loads(r.get('raw_json') or '{}')
    except: pass
    return KufarListing(
        ad_id=r['ad_id'],
        url=r.get('url') or '',
        profile_id=r.get('profile_id') or '',
        price_eur=r.get('price_eur'),
        price_byn=r.get('price_byn'),
        area=r.get('area'),
        rooms=r.get('rooms'),
        floor=r.get('floor'),
        address=r.get('address'),
        title=r.get('title'),
        raw=raw,
    )

def main():
    db=D1(); tg=Telegram()
    chat=db.get_state('telegram_chat_id')
    if not chat:
        raise RuntimeError('Telegram chat is not configured')

    # 1) Real previously recorded discrepancy where the matched Bir object is still active.
    seed=db.query(
      """SELECT e.ad_id,e.object_key
         FROM events e
         JOIN bir_objects b ON b.object_key=e.object_key
         JOIN kufar_ads k ON k.ad_id=e.ad_id
         WHERE e.field_name IN ('price','area','rooms','floor','address')
           AND b.active=1 AND k.active=1
         ORDER BY e.occurred_at DESC LIMIT 1"""
    )
    if seed:
        ad_id=seed[0]['ad_id']; object_key=seed[0]['object_key']
        erows=db.query(
          """SELECT * FROM events
             WHERE ad_id=? AND object_key=?
               AND field_name IN ('price','area','rooms','floor','address')
             ORDER BY occurred_at DESC""",[ad_id,object_key]
        )
        # One latest row per field.
        seen=set(); events=[]
        for e in erows:
            if e['field_name'] in seen: continue
            seen.add(e['field_name']); events.append(e)
        krow=db.query('SELECT * FROM kufar_ads WHERE ad_id=? LIMIT 1',[ad_id])[0]
        tg.send(chat,'🧪 ТЕСТ — объект сейчас есть на Bir\n\n'+fmt_event_group(db,events,k_from_row(krow)))

    # 2) Real historical Bir object that is no longer in current inventory, tied to a Kufar ad.
    gone=db.query(
      """SELECT m.ad_id,m.object_key
         FROM matches m
         JOIN bir_objects b ON b.object_key=m.object_key
         JOIN kufar_ads k ON k.ad_id=m.ad_id
         WHERE b.active=0 AND k.active=1
         ORDER BY b.last_seen_at DESC LIMIT 1"""
    )
    if gone:
        ad_id=gone[0]['ad_id']; object_key=gone[0]['object_key']
        krow=db.query('SELECT * FROM kufar_ads WHERE ad_id=? LIMIT 1',[ad_id])[0]
        event={'field_name':'existence','object_key':object_key,'new_value':'active Kufar','bir_value':'no matching current Bir object'}
        tg.send(chat,'🧪 ТЕСТ — объекта сейчас нет на Bir\n\n'+fmt_event_group(db,[event],k_from_row(krow)))

    if not seed or not gone:
        tg.send(chat,'🧪 Для одного из двух сценариев в сохранённой истории пока не нашлось подходящего реального примера.')

if __name__=='__main__':
    main()
