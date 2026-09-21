import asyncio, json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlparse
from .config import settings
from .d1 import D1
from .telegram import Telegram
from .collectors.kufar import KufarCollector
from .collectors.bir import BirCollector
from .store import save_kufar, save_bir
from .audit import AuditSession
from .matcher import area_close

MINSK=ZoneInfo('Europe/Minsk')
KEYBOARD=[
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

HOUSE_NAMES={
  'andromeda':'Андромеда',
  'atlantik':'Атлантик',
  'dom-atlantik':'Атлантик',
  'dom-everest':'Эверест',
  'dom-kontinental':'Континенталь',
  'dom-mediteranian':'Медитераниан',
  'dom-shtadt-park':'Штадт-парк',
  'kaspian':'Каспиан',
  'lira':'Лира',
  'sirius':'Сириус',
  'vega':'Вега',
}

FRESH_SCOPE_STATE='fresh_scope_v3_applied'

def fmt_num(v, decimals=2):
    if v is None: return '—'
    try:
        n=float(v)
        s=f'{n:,.{decimals}f}'.replace(',',' ').replace('.',',')
        return s.rstrip('0').rstrip(',')
    except: return str(v)

def fmt_area(v):
    if v is None: return '—'
    try: return f"{float(v):.2f}".replace('.',',')
    except: return str(v)

def fmt_eur(v):
    if v is None: return '—'
    try: return f"{float(v):,.0f}".replace(',',' ')+' €'
    except: return str(v)

def fmt_rooms(v):
    try: return str(int(float(v)))
    except: return str(v) if v is not None else '—'

def parse_any_ts(v):
    if v is None or v=='': return None
    try:
        if isinstance(v,(int,float)) or str(v).strip().isdigit():
            n=float(v)
            if n>10_000_000_000: n/=1000.0
            return datetime.fromtimestamp(n,tz=timezone.utc)
        dt=datetime.fromisoformat(str(v).strip().replace('Z','+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except:
        return None

def fmt_dt_minsk(v):
    dt=parse_any_ts(v)
    return dt.astimezone(MINSK).strftime('%d.%m.%Y, %H:%M') if dt else None

def _json_dict(v):
    if isinstance(v,dict): return v
    try:
        out=json.loads(v or '{}')
        return out if isinstance(out,dict) else {}
    except: return {}

def bir_raw_from_row(row):
    return _json_dict(row.get('bir_raw_json') or row.get('raw_json'))

def kufar_raw_from_row(row):
    return _json_dict(row.get('kufar_raw_json'))

def kufar_card_time(raw):
    return fmt_dt_minsk((raw or {}).get('list_time'))

def bir_link_from_row(b):
    raw=bir_raw_from_row(b)
    href=raw.get('house_href')
    if href:
        return urljoin('https://bir.by/',str(href))
    return settings.bir_search_url

def house_label(b):
    raw=bir_raw_from_row(b)
    href=str(raw.get('house_href') or '')
    slug=urlparse(href).path.rstrip('/').split('/')[-1].lower()
    name=HOUSE_NAMES.get(slug)
    number=b.get('building_name')
    if name and number: return f"{name} ({number})"
    return name or number

def event_context(db,e,k):
    b={}
    key=e.get('object_key')
    if key:
        rows=db.query('SELECT * FROM bir_objects WHERE object_key=? LIMIT 1',[key])
        if rows: b=rows[0]
    raw={}
    try: raw=json.loads(b.get('raw_json') or '{}')
    except: pass
    building=house_label(b) or raw.get('house_name') or raw.get('building')
    address=k.address or b.get('official_address') or raw.get('address')
    return b,building,address

def fmt_event_group(db,events,k):
    first=events[0]
    b,building,address=event_context(db,first,k)
    fields={e['field_name']:e for e in events}

    if set(fields)=={'existence'}:
        parts=["🚨 Объявление на Kufar не соответствует наличию на Bir"]
    elif len(fields)==1:
        field=next(iter(fields))
        parts=[f"🚨 {TITLES.get(field,'Расхождение между Kufar и Bir')}"]
    else:
        parts=["🚨 Расхождения между Kufar и Bir"]

    if building: parts.append(f"Дом: {building}")
    if address: parts.append(f"Адрес: {address}")
    if b.get('unit_no'): parts.append(f"Помещение № {b.get('unit_no')}")

    specs=[]
    if k.rooms is not None: specs.append(f"{fmt_rooms(k.rooms)}-комн.")
    if k.area is not None: specs.append(f"{fmt_area(k.area)} м²")
    if k.floor is not None: specs.append(f"{fmt_rooms(k.floor)} этаж")
    if specs: parts.append("Квартира: "+", ".join(specs))

    kufar_time=kufar_card_time(k.raw)
    detected_time=fmt_dt_minsk(first.get('occurred_at'))
    if kufar_time: parts.append(f"Kufar — публикация/обновление: {kufar_time}")
    if detected_time: parts.append(f"Радар обнаружил: {detected_time}")

    if 'existence' in fields:
        last_seen=fmt_dt_minsk(b.get('last_seen_at'))
        parts.append('')
        if last_seen:
            parts.append(f"Последний раз в выдаче Bir: {last_seen}")
        else:
            parts.append("На момент проверки соответствующий объект на Bir не найден.")
    else:
        for field in ['price','area','rooms','floor','address']:
            e=fields.get(field)
            if not e: continue
            parts.append('')
            if field=='price':
                try: bv=json.loads(e.get('bir_value') or '{}')
                except: bv={}
                parts += [
                  "Цена",
                  f"Kufar: {fmt_eur(e.get('new_value'))}",
                  f"Bir: {fmt_eur(bv.get('regular'))}",
                  f"Спеццена Bir: {fmt_eur(bv.get('fast'))}",
                ]
            elif field=='area':
                parts += ["Площадь",f"Kufar: {fmt_area(e.get('new_value'))} м²",f"Bir: {fmt_area(e.get('bir_value'))} м²"]
            elif field=='rooms':
                parts += ["Комнаты",f"Kufar: {fmt_rooms(e.get('new_value'))}",f"Bir: {fmt_rooms(e.get('bir_value'))}"]
            elif field=='floor':
                parts += ["Этаж",f"Kufar: {fmt_rooms(e.get('new_value'))}",f"Bir: {fmt_rooms(e.get('bir_value'))}"]
            elif field=='address':
                parts += ["Адрес",f"Kufar: {e.get('new_value') or '—'}",f"Bir: {e.get('bir_value') or '—'}"]

    if k.url: parts += ['',f"Kufar: {k.url}"]
    if b: parts.append(f"Bir: {bir_link_from_row(b)}")
    return '\n'.join(parts)

def save_diag(db,source,diag):
    ts=datetime.now(timezone.utc).isoformat(); stm=[]; seen=set()
    for row in diag[-10:]:
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
    rows=db.query('SELECT COUNT(*) AS n FROM kufar_ads WHERE active=1 AND profile_id=?',[settings.kufar_profile_id])
    previous_active=int(rows[0]['n']) if rows else 0
    c=KufarCollector(); items=await c.collect(); save_diag(db,'kufar',c.diagnostics)
    changed=save_kufar(db,items,settings.kufar_profile_id)
    db.set_state('last_kufar_success',datetime.now(timezone.utc).isoformat())
    db.set_state('last_kufar_count',str(len(items)))
    return items,changed,previous_active

def choose_audit_targets(items,changed,previous_active):
    total=len(items)
    if not total: return [],'empty_snapshot'
    if previous_active<max(20,int(total*0.50)):
        return [],'baseline_only'
    if len(changed)>max(25,int(total*0.10)):
        return [],'bulk_rebaseline'
    return changed,'incremental'

def archive_legacy_events_once(db):
    if db.get_state(FRESH_SCOPE_STATE,'')=='1': return 0
    rows=db.query('SELECT COUNT(*) AS n FROM events WHERE active=1')
    count=int(rows[0]['n']) if rows else 0
    ts=datetime.now(timezone.utc).isoformat()
    db.batch([
      ('UPDATE events SET active=0,resolved_at=? WHERE active=1',[ts]),
      ('INSERT INTO state(key,value,updated_at) VALUES(?,?,?) '
       'ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',
       [FRESH_SCOPE_STATE,'1',ts]),
      ('INSERT INTO state(key,value,updated_at) VALUES(?,?,?) '
       'ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',
       ['fresh_scope_v3_cutover_at',ts,ts]),
      ('INSERT INTO state(key,value,updated_at) VALUES(?,?,?) '
       'ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',
       ['fresh_scope_v3_archived_events',str(count),ts]),
    ])
    return count

def close_inactive_ad_events(db):
    ts=datetime.now(timezone.utc).isoformat()
    db.execute(
      'UPDATE events SET active=0,resolved_at=? WHERE active=1 AND occurred_at>=? '
      'AND ad_id IN (SELECT ad_id FROM kufar_ads WHERE active=0)',
      [ts,settings.live_cutoff_utc]
    )

def close_rounded_area_events(db):
    rows=db.query(
      '''SELECT e.id, k.area AS kufar_area, b.area AS bir_area
         FROM events e
         JOIN kufar_ads k ON k.ad_id=e.ad_id
         JOIN bir_objects b ON b.object_key=e.object_key
         WHERE e.active=1 AND e.field_name='area' AND e.occurred_at>=?''',
      [settings.live_cutoff_utc]
    )
    ids=[r['id'] for r in rows if area_close(r.get('kufar_area'),r.get('bir_area'))]
    ts=datetime.now(timezone.utc).isoformat()
    for i in range(0,len(ids),75):
        db.batch([('UPDATE events SET active=0,resolved_at=? WHERE id=?',[ts,event_id]) for event_id in ids[i:i+75]])
    return len(ids)

def active_event_count(db):
    rows=db.query('SELECT COUNT(*) AS n FROM events WHERE active=1 AND occurred_at>=?',[settings.live_cutoff_utc])
    return int(rows[0]['n']) if rows else 0

def active_event_counts(db):
    rows=db.query(
      'SELECT field_name, COUNT(*) AS n FROM events '
      'WHERE active=1 AND occurred_at>=? GROUP BY field_name ORDER BY field_name',
      [settings.live_cutoff_utc]
    )
    return {r['field_name']: int(r['n']) for r in rows}

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
                k.raw_json AS kufar_raw_json,
                b.building_name, b.official_address, b.unit_no,
                b.raw_json AS bir_raw_json
         FROM events e
         JOIN kufar_ads k ON k.ad_id=e.ad_id
         LEFT JOIN bir_objects b ON b.object_key=e.object_key
         WHERE e.active=1 AND k.active=1 AND e.occurred_at>=?
         ORDER BY e.occurred_at DESC''',
      [settings.live_cutoff_utc]
    )

def comparison_line(r):
    field=r.get('field_name')
    if field=='price':
        try: bir=json.loads(r.get('bir_value') or '{}')
        except: bir={}
        regular=fmt_eur(bir.get('regular'))
        fast=fmt_eur(bir.get('fast'))
        bir_text=regular
        if bir.get('fast') is not None and fast!=regular:
            bir_text=f"{regular} (спец.: {fast})"
        return f"Kufar: {fmt_eur(r.get('new_value'))} | Bir: {bir_text}"
    if field=='area':
        return f"Kufar: {fmt_area(r.get('new_value'))} м² | Bir: {fmt_area(r.get('bir_value'))} м²"
    if field=='rooms':
        return f"Kufar: {fmt_rooms(r.get('new_value'))} комн. | Bir: {fmt_rooms(r.get('bir_value'))} комн."
    if field=='floor':
        return f"Kufar: {fmt_rooms(r.get('new_value'))} этаж | Bir: {fmt_rooms(r.get('bir_value'))} этаж"
    if field=='address':
        return f"Kufar: {r.get('new_value') or '—'} | Bir: {r.get('bir_value') or '—'}"
    if field=='existence':
        return "Kufar: объявление активно | Bir: соответствующего объекта нет"
    return None

def summary_line(r):
    building=house_label(r)
    address=r.get('address') or r.get('official_address')
    bits=[]
    if building: bits.append(str(building))
    if address and (not building or address.casefold() not in str(building).casefold()): bits.append(str(address))
    if r.get('unit_no'): bits.append(f"пом. № {r.get('unit_no')}")
    if r.get('rooms') is not None: bits.append(f"{fmt_rooms(r.get('rooms'))}-комн.")
    if r.get('area') is not None: bits.append(f"{fmt_area(r.get('area'))} м²")
    if r.get('floor') is not None: bits.append(f"{fmt_rooms(r.get('floor'))} эт.")
    label=', '.join(bits) if bits else 'Объявление'
    bir_url=bir_link_from_row(r) if r.get('object_key') else None
    comparison=comparison_line(r)
    links=[x for x in [f"Kufar — {r.get('url')}" if r.get('url') else None, f"Bir — {bir_url}" if bir_url else None] if x]
    details=[]
    if comparison: details.append(comparison)
    kufar_time=kufar_card_time(kufar_raw_from_row(r))
    detected_time=fmt_dt_minsk(r.get('occurred_at'))
    times=[]
    if kufar_time: times.append(f"Kufar: {kufar_time}")
    if detected_time: times.append(f"радар: {detected_time}")
    if times: details.append("Время — "+" | ".join(times))
    if links: details.append("Ссылки: "+" | ".join(links))
    return ("• "+label+("\n  "+"\n  ".join(details) if details else "")).rstrip()

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
        for msg in chunks:
            tg.send(chat,msg)

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
    items,changed,previous_active=await collect_kufar(db)
    targets,selection_mode=choose_audit_targets(items,changed,previous_active)
    archived_legacy_events=archive_legacy_events_once(db)
    close_inactive_ad_events(db)
    rounded_area_events_closed=close_rounded_area_events(db)
    print(
      f"RADAR_INPUT bir_refreshed={bir_changed} kufar_alena={len(items)} previous_active={previous_active} "
      f"changed={len(changed)} targets={len(targets)} selection_mode={selection_mode} "
      f"archived_legacy_events={archived_legacy_events} "
      f"rounded_area_events_closed={rounded_area_events_closed} "
    )

    # Only incremental NEW/EDITED/REAPPEARED cards are audited. A first or
    # suspiciously large snapshot becomes a silent baseline instead.
    session=AuditSession(db)
    all_new=[]
    for k in targets:
        r=session.audit(k)
        for e in session.sync(k,r):
            all_new.append((e,k))
    statements=session.flush()
    active_by_field=active_event_counts(db)
    print(
      f"RADAR_RESULT targets={len(targets)} new_events={len(all_new)} "
      f"active_events={sum(active_by_field.values())} active_by_field={active_by_field} statements={statements}"
    )

    local_now=datetime.now(MINSK)
    morning=False
    if chat and should_send_morning_summary(db,local_now):
        send_state_summary(db,tg,chat,keyboard=True)
        db.set_state('morning_summary_date',local_now.date().isoformat())
        morning=True

    if chat and should_live_notify(local_now) and not morning:
        grouped={}
        for e,k in all_new:
            grouped.setdefault(k.ad_id,{'k':k,'events':[]})['events'].append(e)
        for item in grouped.values():
            tg.send(chat,fmt_event_group(db,item['events'],item['k']))

    if chat and show:
        send_state_summary(db,tg,chat,keyboard=True)

    if chat and force:
        tg.send(
          chat,
          f"✅ Проверка завершена. Новых/изменённых объявлений для проверки: {len(targets)}. "
          f"Сейчас требуют внимания: {active_event_count(db)}.",
          KEYBOARD
        )

if __name__=='__main__':
    asyncio.run(run())
