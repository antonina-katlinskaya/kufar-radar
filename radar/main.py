import asyncio, json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from .config import settings
from .d1 import D1
from .telegram import Telegram
from .collectors.kufar import KufarCollector
from .collectors.bir import BirCollector
from .store import save_kufar, save_bir
from .audit import AuditSession

MINSK=ZoneInfo('Europe/Minsk')
KEYBOARD=[
  [{'text':'🔎 Проверить сейчас','callback_data':'check_now'}],
  [{'text':'📋 Актуальное состояние','callback_data':'state_now'}]
]

TITLES={
  'price':'Цена на Kufar не совпадает с Bir',
  'area':'Расхождение по площади между Kufar и Bir',
  'rooms':'Расхождение по количеству комнат между Kufar и Bir',
  'floor':'Расхождение по этажу между Kufar и Bir',
  'address':'Расхождение по адресу между Kufar и Bir',
  'existence':'Объявление на Kufar не соответствует наличию на Bir',
}

def fmt_num(v, decimals=2):
    if v is None: return '—'
    try:
        n=float(v)
        s=f'{n:,.{decimals}f}'.replace(',',' ').replace('.',',')
        return s.rstrip('0').rstrip(',')
    except: return str(v)

def fmt_eur(v):
    if v is None: return '—'
    try: return f"{float(v):,.0f}".replace(',',' ')+' €'
    except: return str(v)

def fmt_rooms(v):
    try: return str(int(float(v)))
    except: return str(v) if v is not None else '—'

def event_context(db,e,k):
    b={}
    key=e.get('object_key')
    if key:
        rows=db.query('SELECT * FROM bir_objects WHERE object_key=? LIMIT 1',[key])
        if rows: b=rows[0]
    building=b.get('building_name')
    address=k.address or b.get('official_address')
    return b,building,address

def fmt_event(db,e,k):
    field=e['field_name']; b,building,address=event_context(db,e,k)
    parts=[f"🚨 {TITLES.get(field,'Расхождение между Kufar и Bir')}"]
    if building: parts.append(f"Дом: {building}")
    if address: parts.append(f"Адрес: {address}")

    specs=[]
    if k.rooms is not None: specs.append(f"{fmt_rooms(k.rooms)}-комн.")
    if k.area is not None: specs.append(f"{fmt_num(k.area)} м²")
    if k.floor is not None: specs.append(f"{fmt_rooms(k.floor)} этаж")
    if specs: parts.append("Квартира: "+", ".join(specs))

    if field=='price':
        try: bv=json.loads(e.get('bir_value') or '{}')
        except: bv={}
        parts += [
          '',
          f"Kufar: {fmt_eur(e.get('new_value'))}",
          f"Bir: {fmt_eur(bv.get('regular'))}",
          f"Спеццена Bir: {fmt_eur(bv.get('fast'))}",
        ]
    elif field=='area':
        parts += ['',f"Kufar: {fmt_num(e.get('new_value'))} м²",f"Bir: {fmt_num(e.get('bir_value'))} м²"]
    elif field=='rooms':
        parts += ['',f"Kufar: {fmt_rooms(e.get('new_value'))} комн.",f"Bir: {fmt_rooms(e.get('bir_value'))} комн."]
    elif field=='floor':
        parts += ['',f"Kufar: {fmt_rooms(e.get('new_value'))} этаж",f"Bir: {fmt_rooms(e.get('bir_value'))} этаж"]
    elif field=='address':
        parts += ['',f"Kufar: {e.get('new_value') or '—'}",f"Bir: {e.get('bir_value') or '—'}"]
    elif field=='existence':
        parts += ['','На момент проверки соответствующий объект на Bir не найден.']

    if k.url: parts += ['',k.url]
    return '\n'.join(parts)

def save_diag(db,source,diag):
    ts=datetime.now(timezone.utc).isoformat(); stm=[]; seen=set()
    for row in diag[-100:]:
        url=row[0] if len(row)>0 else None
        method=row[1] if len(row)>1 else None
        status=row[2] if len(row)>2 else None
        ct=row[3] if len(row)>3 else None
        note=' | '.join(str(x) for x in row[4:]) if len(row)>4 else None
        key=(url,method,status,ct,note)
        if key in seen: continue
        seen.add(key)
        stm.append(('INSERT INTO source_diagnostics(source,observed_at,url,method,status,content_type,note) VALUES(?,?,?,?,?,?,?)',[source,ts,url,method,status,ct,note]))
    for i in range(0,len(stm),75): db.batch(stm[i:i+75])

def parse_ts(v):
    try: return datetime.fromisoformat(v.replace('Z','+00:00'))
    except: return None

async def collect_bir(db,force=False):
    last=db.get_state('last_bir_success')
    if not force and last:
        dt=parse_ts(last)
        if dt and datetime.now(timezone.utc)-dt < timedelta(minutes=settings.bir_refresh_minutes):
            return False
    c=BirCollector(); items=await c.collect(); save_diag(db,'bir',c.diagnostics); save_bir(db,items)
    db.set_state('last_bir_success',datetime.now(timezone.utc).isoformat())
    db.set_state('last_bir_count',str(len(items)))
    return True

async def collect_kufar(db):
    c=KufarCollector(); items=await c.collect(); save_diag(db,'kufar',c.diagnostics)
    changed=save_kufar(db,items,settings.kufar_profile_id)
    db.set_state('last_kufar_success',datetime.now(timezone.utc).isoformat())
    db.set_state('last_kufar_count',str(len(items)))
    return items,changed

def close_inactive_ad_events(db):
    ts=datetime.now(timezone.utc).isoformat()
    db.execute(
      'UPDATE events SET active=0,resolved_at=? WHERE active=1 '
      'AND ad_id IN (SELECT ad_id FROM kufar_ads WHERE active=0)',
      [ts]
    )

def active_event_count(db):
    rows=db.query('SELECT COUNT(*) AS n FROM events WHERE active=1')
    return int(rows[0]['n']) if rows else 0

def process_updates(db,tg):
    offset=int(db.get_state('telegram_offset','0') or 0); force=False; show=False
    ups=tg.get_updates(offset)
    for u in ups:
        offset=max(offset,int(u['update_id'])+1)
        if 'message' in u:
            m=u['message']; cid=str(m['chat']['id']); txt=m.get('text','')
            allowed=db.get_state('telegram_chat_id')
            if not allowed and m['chat'].get('type')=='private':
                db.set_state('telegram_chat_id',cid); allowed=cid
            if cid!=allowed: continue
            if txt.startswith('/start'):
                tg.send(cid,'Радар подключён. Новые и изменённые объявления будут проверяться автоматически.',KEYBOARD)
            elif txt.startswith('/check'):
                force=True
            elif txt.startswith('/state') or txt.startswith('/violations'):
                show=True
        elif 'callback_query' in u:
            q=u['callback_query']; cid=str(q['message']['chat']['id']); allowed=db.get_state('telegram_chat_id')
            if cid!=allowed: continue
            tg.answer_callback(q['id'])
            if q.get('data')=='check_now': force=True
            if q.get('data') in {'state_now','violations'}: show=True
    db.set_state('telegram_offset',str(offset))
    return force,show

def summary_rows(db):
    return db.query(
      '''SELECT e.*, k.url, k.address, k.area, k.rooms, k.floor,
                b.building_name, b.official_address
         FROM events e
         JOIN kufar_ads k ON k.ad_id=e.ad_id
         LEFT JOIN bir_objects b ON b.object_key=e.object_key
         WHERE e.active=1 AND k.active=1
         ORDER BY e.occurred_at DESC
         LIMIT 250'''
    )

def summary_line(r):
    building=r.get('building_name')
    address=r.get('address') or r.get('official_address')
    bits=[]
    if building: bits.append(str(building))
    if address and (not building or address.casefold() not in str(building).casefold()): bits.append(str(address))
    if r.get('rooms') is not None: bits.append(f"{fmt_rooms(r.get('rooms'))}-комн.")
    if r.get('area') is not None: bits.append(f"{fmt_num(r.get('area'))} м²")
    if r.get('floor') is not None: bits.append(f"{fmt_rooms(r.get('floor'))} эт.")
    label=', '.join(bits) if bits else 'Объявление'
    return f"• {label}\n  {r.get('url') or ''}".rstrip()

def send_state_summary(db,tg,chat,keyboard=True):
    rows=summary_rows(db)
    title='📋 Актуальное состояние объявлений на Kufar'
    if not rows:
        tg.send(chat,title+'\n\nРасхождений, требующих внимания, сейчас нет.',KEYBOARD if keyboard else None)
        return

    grouped={}
    for r in rows: grouped.setdefault(r['field_name'],[]).append(r)
    total=len(rows)
    first=True
    order=['price','area','rooms','floor','address','existence']
    for field in order:
        group=grouped.get(field) or []
        if not group: continue
        header=(title+f"\n\nВсего требуют внимания: {total}\n\n" if first else '')+f"{TITLES.get(field,field)} — {len(group)}"
        first=False
        chunks=[]; cur=header
        for r in group:
            line='\n\n'+summary_line(r)
            if len(cur)+len(line)>3600:
                chunks.append(cur); cur=f"{TITLES.get(field,field)} — продолжение"+line
            else:
                cur+=line
        chunks.append(cur)
        for i,msg in enumerate(chunks):
            tg.send(chat,msg,KEYBOARD if keyboard and field==order[-1] and i==len(chunks)-1 else None)

    # If the last predefined category was absent, ensure controls are still easy to reach.
    if keyboard:
        tg.send(chat,'Управление радаром:',KEYBOARD)

def should_live_notify(local_now):
    return 8 <= local_now.hour < 21

def should_send_morning_summary(db,local_now):
    if not (8 <= local_now.hour < 9): return False
    today=local_now.date().isoformat()
    return db.get_state('morning_summary_date','') != today

async def run():
    db=D1(); tg=Telegram()
    force,show=process_updates(db,tg)
    chat=db.get_state('telegram_chat_id')

    bir_changed=await collect_bir(db,force=force)
    items,changed=await collect_kufar(db)
    close_inactive_ad_events(db)
    print(f"RADAR_INPUT bir_refreshed={bir_changed} kufar_alena={len(items)} changed={len(changed)}")

    # Core rule: only a NEW or EDITED Kufar card is audited.
    targets=changed
    session=AuditSession(db)
    all_new=[]
    for k in targets:
        r=session.audit(k)
        for e in session.sync(k,r):
            all_new.append((e,k))
    statements=session.flush()
    print(f"RADAR_RESULT targets={len(targets)} new_events={len(all_new)} active_events={active_event_count(db)} statements={statements}")

    local_now=datetime.now(MINSK)
    morning=False
    if chat and should_send_morning_summary(db,local_now):
        send_state_summary(db,tg,chat,keyboard=True)
        db.set_state('morning_summary_date',local_now.date().isoformat())
        morning=True

    if chat and should_live_notify(local_now) and not morning:
        # Deliberately send one clean Telegram card per discrepancy.
        for e,k in all_new:
            tg.send(chat,fmt_event(db,e,k))

    if chat and show:
        send_state_summary(db,tg,chat,keyboard=True)

    if chat and force:
        tg.send(
          chat,
          f"✅ Проверка завершена. Новых/изменённых объявлений: {len(changed)}. "
          f"Сейчас требуют внимания: {active_event_count(db)}.",
          KEYBOARD
        )

if __name__=='__main__':
    asyncio.run(run())
