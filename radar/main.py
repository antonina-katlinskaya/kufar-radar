import asyncio, json, secrets
import html, re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urljoin, urlparse
from .config import settings, KUFAR_PROFILES
from .d1 import D1
from .telegram import Telegram
from .collectors.kufar import KufarCollector
from .collectors.bir import BirCollector
from .store import save_kufar, save_bir
from .audit import AuditSession
from .matcher import area_close

MINSK=ZoneInfo('Europe/Minsk')
CHECK_BUTTON='🔄 Проверить сейчас'
MAIN_KEYBOARD=[[CHECK_BUTTON]]
# Versioned state deliberately forces a one-time owner-only keyboard restore.
KEYBOARD_STATE='telegram_main_keyboard_v5_owner_only_sent'
SUBSCRIBERS_STATE='telegram_chat_ids_v1'
INVITE_TOKEN_STATE='telegram_invite_token_v1'
INVITE_NOTICE_STATE='telegram_sister_invite_v1_sent'
BOT_USERNAME='kufar_radarr_bot'

TITLES={
  'price':'Цена на Kufar не совпадает с BIR',
  'area':'Расхождение по площади между Kufar и BIR',
  'rooms':'Расхождение по количеству комнат между Kufar и BIR',
  'floor':'Расхождение по этажу между Kufar и BIR',
  'address':'Расхождение по адресу между Kufar и BIR',
  'existence':'Объявление на Kufar не соответствует наличию на BIR',
  'review':'Нужна ручная проверка сопоставления',
}

CARD_TITLES={
  'price':'НЕ СОВПАДАЕТ ЦЕНА',
  'area':'НЕ СОВПАДАЕТ ПЛОЩАДЬ',
  'rooms':'НЕ СОВПАДАЕТ КОЛИЧЕСТВО КОМНАТ',
  'floor':'НЕ СОВПАДАЕТ ЭТАЖ',
  'address':'НЕ СОВПАДАЕТ АДРЕС',
  'existence':'ОБЪЕКТА НЕТ НА BIR',
  'review':'НУЖНА РУЧНАЯ ПРОВЕРКА',
}

FIELD_LABELS={
  'price':'Цена',
  'area':'Площадь',
  'rooms':'Комнаты',
  'floor':'Этаж',
  'address':'Адрес',
  'existence':'Нет на BIR',
  'review':'Нужна проверка',
}

FIELD_ICONS={
  'price':'💶',
  'area':'📐',
  'rooms':'🚪',
  'floor':'🏢',
  'address':'📍',
  'existence':'❌',
  'review':'🟡',
}

HOUSE_NAMES={
  'atlantik':'Атлантик',
  'dom-atlantik':'Атлантик',
  'dom-everest':'Эверест',
  'dom-kontinental':'Континенталь',
  'dom-mediteranian':'Медитераниан',
  'dom-shtadt-park':'Штадт-парк',
  'kaspian':'Каспиан', 'dom-kaspian':'Каспиан',
  'lira':'Лира', 'dom-lira':'Лира',
  'orion':'Орион', 'dom-orion':'Орион',
  'andromeda':'Андромеда', 'dom-andromeda':'Андромеда',
  'sirius':'Сириус', 'dom-sirius':'Сириус',
  'vega':'Вега', 'dom-vega':'Вега',
  'kalemegdan':'Калемегдан', 'dom-kalemegdan':'Калемегдан',
  'sad-ermitazh':'Сад Эрмитаж', 'dom-sad-ermitazh':'Сад Эрмитаж',
}

FRESH_SCOPE_STATE='fresh_scope_v3_applied'
PENDING_AUDITS_STATE='pending_audits_v1'
STRICT_ADDRESS_RECHECK_STATE='strict_address_v3_recheck_done'
STRICT_BACKFILL_CLEANUP_STATE='strict_address_v2_cleanup_done'
STRICT_BACKFILL_CUTOFF='2026-09-24T13:05:00+00:00'
RELIABLE_VERSIONS_CUTOFF='2026-09-24T13:01:00+00:00'
AUDIT_BATCH_LIMIT=200
ACTIONABLE_FIELDS={'price','area'}
SERVICE_FIELDS=('address','floor','rooms','existence','review')

PROFILE_LABELS={p['id']:p['label'] for p in KUFAR_PROFILES}

def profile_label(profile_id):
    return PROFILE_LABELS.get(str(profile_id),f'Профиль {profile_id}')

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

def fmt_short_dt_minsk(v):
    dt=parse_any_ts(v)
    return dt.astimezone(MINSK).strftime('%d.%m %H:%M') if dt else None

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

def telegram_html(text):
    escaped=html.escape(str(text),quote=False)
    return re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',escaped)

def bot_action(text):
    value=(text or '').strip()
    if value.startswith('/invite'): return 'invite'
    if value.startswith('/start'): return 'start'
    if value.startswith('/check') or value==CHECK_BUTTON: return 'check'
    if value.startswith('/state') or value.startswith('/violations') or value=='📋 Показать расхождения': return 'state'
    return None

def start_payload(text):
    match=re.match(r'^/start(?:@\w+)?(?:\s+([A-Za-z0-9_-]{1,64}))?\s*$',(text or '').strip())
    return match.group(1) if match else None

def subscribed_chat_ids(db):
    values=[]
    legacy=db.get_state('telegram_chat_id')
    if legacy: values.append(str(legacy))
    try:
        stored=json.loads(db.get_state(SUBSCRIBERS_STATE,'[]') or '[]')
        if isinstance(stored,list): values += [str(v) for v in stored if v is not None]
    except: pass
    return list(dict.fromkeys(values))

def automatic_chat_ids(db):
    """Automatic summaries and alerts go only to the bot owner.

    Other invited subscribers keep access to the persistent button and receive
    a report only when they request it themselves.
    """
    owner=db.get_state('telegram_chat_id')
    return [str(owner)] if owner else []

def add_subscriber(db,chat_id):
    chat_id=str(chat_id)
    values=subscribed_chat_ids(db)
    if chat_id not in values:
        values.append(chat_id)
        db.set_state(SUBSCRIBERS_STATE,json.dumps(values,separators=(',',':')))
    return values

def create_invite(db):
    token=secrets.token_urlsafe(24)
    db.set_state(INVITE_TOKEN_STATE,token)
    return f'https://t.me/{BOT_USERNAME}?start={token}'

def consume_invite(db,chat_id,payload):
    expected=db.get_state(INVITE_TOKEN_STATE,'')
    if not payload or not expected or not secrets.compare_digest(str(payload),str(expected)):
        return False
    add_subscriber(db,chat_id)
    db.set_state(INVITE_TOKEN_STATE,'')
    return True

def send_invite(db,tg,owner_chat):
    url=create_invite(db)
    tg.send(
      owner_chat,
      '👭 Ссылка для подключения сестры\n\n'
      'Перешлите ей эту ссылку. Она нажмёт «Старт» и получит кнопку '
      '«🔄 Проверить сейчас». Автоматические уведомления будут приходить только владельцу бота.\n\n'
      f'{url}\n\nСсылка одноразовая: посторонний человек подключиться по ней не сможет после её использования.'
    )
    return url

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

def card_house_label(b):
    raw=bir_raw_from_row(b)
    href=str(raw.get('house_href') or '')
    slug=urlparse(href).path.rstrip('/').split('/')[-1].lower()
    name=HOUSE_NAMES.get(slug)
    number=b.get('building_name')
    if name and number: return f"{name} · дом {number}"
    return name or (f"Дом {number}" if number else None)

def link_keyboard(kufar_url=None,bir_url=None):
    buttons=[]
    if kufar_url: buttons.append({'text':'Открыть Kufar','url':str(kufar_url)})
    if bir_url: buttons.append({'text':'Открыть BIR','url':str(bir_url)})
    return [buttons] if buttons else None

def object_identity_lines(building,address,unit_no,rooms,area,floor,omit_fields=None):
    omit=set(omit_fields or [])
    parts=[]
    if building: parts.append(f"🏢 **{building}**")
    if address: parts.append(f"📍 {address}")
    specs=[]
    if unit_no: specs.append(f"Помещение № {unit_no}")
    if rooms is not None and 'rooms' not in omit: specs.append(f"{fmt_rooms(rooms)}-комн.")
    if area is not None and 'area' not in omit: specs.append(f"{fmt_area(area)} м²")
    if floor is not None and 'floor' not in omit: specs.append(f"{fmt_rooms(floor)} этаж")
    if specs: parts.append("🚪 "+" · ".join(specs))
    return parts

def comparison_lines(row,include_label=False):
    field=row.get('field_name')
    parts=[]
    if include_label:
        parts.append(f"{FIELD_ICONS.get(field,'⚠️')} **{FIELD_LABELS.get(field,field).upper()}**")
    if field=='price':
        try: bir=json.loads(row.get('bir_value') or '{}')
        except: bir={}
        parts += [
          f"**Kufar: {fmt_eur(row.get('new_value'))}**",
          f"**BIR: {fmt_eur(bir.get('regular'))}**",
        ]
        if bir.get('fast') is not None and fmt_eur(bir.get('fast'))!=fmt_eur(bir.get('regular')):
            parts.append(f"**Спеццена BIR: {fmt_eur(bir.get('fast'))}**")
    elif field=='area':
        parts += [f"**Kufar: {fmt_area(row.get('new_value'))} м²**",f"**BIR: {fmt_area(row.get('bir_value'))} м²**"]
    elif field=='rooms':
        parts += [f"**Kufar: {fmt_rooms(row.get('new_value'))} комн.**",f"**BIR: {fmt_rooms(row.get('bir_value'))} комн.**"]
    elif field=='floor':
        parts += [f"**Kufar: {fmt_rooms(row.get('new_value'))} этаж**",f"**BIR: {fmt_rooms(row.get('bir_value'))} этаж**"]
    elif field=='address':
        parts += [f"**Kufar: {row.get('new_value') or '—'}**",f"**BIR: {row.get('bir_value') or '—'}**"]
    elif field=='existence':
        parts += ["**Kufar: объявление активно**","**BIR: объект не найден**"]
    elif field=='review':
        parts += ["**Автоматически сопоставить квартиру не удалось**",f"Причина: {row.get('bir_value') or 'недостаточно данных'}"]
    return parts

def probable_event(row):
    return row.get('event_type')=='PROBABLE_MISMATCH'

def display_card_title(field,probable=False):
    title=CARD_TITLES.get(field,'НАЙДЕНО РАСХОЖДЕНИЕ')
    return f'ВЕРОЯТНО: {title}' if probable else title

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

    all_probable=bool(events) and all(probable_event(event) for event in events)
    marker='🟡' if set(fields)=={'review'} else ('🟠' if all_probable else '🔴')
    if len(fields)==1:
        field=next(iter(fields))
        parts=[f"{marker} **{display_card_title(field,all_probable)}**"]
    else:
        parts=[f"{marker} **{'ВЕРОЯТНЫЕ РАСХОЖДЕНИЯ' if all_probable else 'НЕСКОЛЬКО РАСХОЖДЕНИЙ'}**"]

    parts += ['',f"👤 **{profile_label(k.profile_id)}**"]
    parts += object_identity_lines(
      card_house_label(b) or building,address,b.get('unit_no'),
      k.rooms,k.area,k.floor,omit_fields=set(fields)
    )

    for field in ['price','area','rooms','floor','address','existence','review']:
        e=fields.get(field)
        if not e: continue
        parts.append('')
        parts += comparison_lines(e,include_label=len(fields)>1)

    kufar_time=fmt_short_dt_minsk((k.raw or {}).get('list_time'))
    detected_time=fmt_short_dt_minsk(first.get('occurred_at'))
    bir_checked_time=fmt_short_dt_minsk(db.get_state('last_bir_success'))
    times=[]
    if kufar_time: times.append(f"Kufar {kufar_time}")
    if detected_time: times.append(f"радар {detected_time}")
    if bir_checked_time: times.append(f"BIR {bir_checked_time}")
    if times: parts += ['',"🕒 "+" · ".join(times)]
    return '\n'.join(parts)

def event_link_keyboard(db,event,k):
    b,_,_=event_context(db,event,k)
    bir_url=bir_link_from_row(b) if b else settings.bir_search_url
    return link_keyboard(k.url,bir_url)

def compact_comparison(row):
    field=row.get('field_name')
    if field=='price':
        try: bir=json.loads(row.get('bir_value') or '{}')
        except: bir={}
        return f"{fmt_eur(row.get('new_value'))} → {fmt_eur(bir.get('regular') or bir.get('fast'))}"
    if field=='area': return f"{fmt_area(row.get('new_value'))} → {fmt_area(row.get('bir_value'))} м²"
    if field=='rooms': return f"{fmt_rooms(row.get('new_value'))} → {fmt_rooms(row.get('bir_value'))} комн."
    if field=='floor': return f"{fmt_rooms(row.get('new_value'))} → {fmt_rooms(row.get('bir_value'))} этаж"
    if field=='address': return f"{row.get('new_value') or '—'} → {row.get('bir_value') or '—'}"
    if field=='existence': return 'активно → объекта нет на BIR'
    return str(row.get('bir_value') or 'нужна проверка')

def fmt_mass_event_group(field,profile_id,records):
    all_probable=bool(records) and all(probable_event(row) for row,_ in records)
    marker='🟡' if field=='review' else ('🟠' if all_probable else '🔴')
    parts=[
      f"{marker} **{display_card_title(field,all_probable)} — {len(records)}**",'',
      f"👤 **{profile_label(profile_id)}**",
      'Однотипные изменения собраны в одно уведомление:',
    ]
    for row,k in records[:12]:
        parts.append(f"• № {k.ad_id}: {compact_comparison(row)}")
        if k.url: parts.append(str(k.url))
    if len(records)>12:
        parts.append(f"…и ещё {len(records)-12}. Полный список доступен по кнопке проверки.")
    return '\n'.join(parts)

def split_mass_records(records,min_size=5):
    grouped={}
    for row,k in records:
        key=(str(k.profile_id),row.get('field_name'))
        grouped.setdefault(key,[]).append((row,k))
    mass=[]; singles=[]
    for (profile_id,field),group in grouped.items():
        if len(group)>=min_size:
            mass.append((field,profile_id,group))
        else:
            singles.extend(group)
    return mass,singles

def actionable_event_records(records):
    return [
      (event,item) for event,item in records
      if event.get('field_name') in ACTIONABLE_FIELDS
    ]

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

async def collect_kufar(db,profile):
    profile_id=profile['id']
    rows=db.query('SELECT COUNT(*) AS n FROM kufar_ads WHERE active=1 AND profile_id=?',[profile_id])
    previous_active=int(rows[0]['n']) if rows else 0
    c=KufarCollector(profile_id,profile.get('contact_person'))
    items=await c.collect(); save_diag(db,f'kufar:{profile_id}',c.diagnostics)
    changed=save_kufar(db,items,profile_id)
    db.set_state('last_kufar_success',datetime.now(timezone.utc).isoformat())
    db.set_state(f'last_kufar_count:{profile_id}',str(len(items)))
    return items,changed,previous_active

def listing_is_today(item,local_now=None):
    local_now=local_now or datetime.now(MINSK)
    dt=parse_any_ts((item.raw or {}).get('list_time'))
    return bool(dt and dt.astimezone(MINSK).date()==local_now.astimezone(MINSK).date())

def choose_audit_targets(items,changed,previous_active,audit_today_on_baseline=False,local_now=None):
    total=len(items)
    if not total: return [],'empty_snapshot'
    if previous_active<max(20,int(total*0.50)):
        if audit_today_on_baseline:
            fresh=[item for item in changed if listing_is_today(item,local_now)]
            return fresh,'baseline_today_only'
        return [],'baseline_only'
    if len(changed)>max(25,int(total*0.10)):
        return changed,'bulk_incremental'
    return changed,'incremental'

def include_active_event_targets(items,targets,active_ad_ids):
    """Include selected current ads without duplicating already selected targets."""
    out=list(targets); seen={item.ad_id for item in out}
    wanted={str(ad_id) for ad_id in active_ad_ids}
    for item in items:
        if item.ad_id in wanted and item.ad_id not in seen:
            out.append(item); seen.add(item.ad_id)
    return out

def load_pending_audits(db):
    try:
        value=json.loads(db.get_state(PENDING_AUDITS_STATE,'{}') or '{}')
        return value if isinstance(value,dict) else {}
    except (TypeError,ValueError):
        return {}

def save_pending_audits(db,pending):
    db.set_state(PENDING_AUDITS_STATE,json.dumps(pending,ensure_ascii=False,separators=(',',':')))

def enqueue_pending_audits(pending,items,reason='new_or_changed'):
    ts=datetime.now(timezone.utc).isoformat()
    for item in items:
        old=pending.get(item.ad_id) or {}
        pending[item.ad_id]={
          'profile_id':str(item.profile_id),'reason':reason,
          'first_queued_at':old.get('first_queued_at') or ts,
          'last_queued_at':ts,'attempts':int(old.get('attempts') or 0),
        }
    return pending

def reliable_today_version_ad_ids(db,local_now=None):
    local_now=local_now or datetime.now(MINSK)
    midnight=datetime.combine(
      local_now.date(),datetime.min.time(),tzinfo=MINSK
    ).astimezone(timezone.utc).isoformat()
    start=max(midnight,RELIABLE_VERSIONS_CUTOFF)
    rows=db.query('SELECT DISTINCT ad_id FROM kufar_versions WHERE observed_at>=?',[start])
    return {str(row['ad_id']) for row in rows}

def cleanup_polluted_strict_backfill(db,pending):
    """Undo v1 backfill fed by legacy FX-noisy versions; fresh cards are re-audited below."""
    if db.get_state(STRICT_BACKFILL_CLEANUP_STATE,'')=='1':
        return 0
    polluted={ad_id for ad_id,row in pending.items() if row.get('reason')=='strict_address_recheck'}
    for ad_id in polluted:
        pending.pop(ad_id,None)
    ts=datetime.now(timezone.utc).isoformat()
    db.execute(
      'UPDATE events SET active=0,resolved_at=? WHERE active=1 AND occurred_at>=?',
      [ts,STRICT_BACKFILL_CUTOFF]
    )
    db.set_state(STRICT_BACKFILL_CLEANUP_STATE,'1')
    return len(polluted)

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

def active_event_type_counts(db):
    rows=db.query(
      'SELECT event_type, COUNT(*) AS n FROM events '
      'WHERE active=1 AND occurred_at>=? GROUP BY event_type ORDER BY event_type',
      [settings.live_cutoff_utc]
    )
    return {r['event_type']:int(r['n']) for r in rows}

def process_updates(db,tg):
    offset=int(db.get_state('telegram_offset','0') or 0)
    force_chats=set(); show_chats=set(); joined_chats=set()
    ups=tg.get_updates(offset)
    for u in ups:
        offset=max(offset,int(u['update_id'])+1)
        if 'message' in u:
            m=u['message']; cid=str(m['chat']['id']); txt=m.get('text','')
            action=bot_action(txt)
            owner=db.get_state('telegram_chat_id')
            if not owner and action=='start' and m['chat'].get('type')=='private':
                db.set_state('telegram_chat_id',cid)
                add_subscriber(db,cid)
                owner=cid
            allowed=set(subscribed_chat_ids(db))

            if cid not in allowed:
                if action=='start' and m['chat'].get('type')=='private' and consume_invite(db,cid,start_payload(txt)):
                    joined_chats.add(cid)
                    tg.send(
                      cid,
                      'Радар подключён. Автоматические уведомления получает владелец бота. '
                      'Вы можете получить актуальную сводку кнопкой ниже.',
                      reply_keyboard=MAIN_KEYBOARD
                    )
                elif action=='start':
                    tg.send(cid,'Этот радар закрытый. Для подключения нужна действующая пригласительная ссылка.')
                continue

            if action=='start':
                is_owner=cid==str(owner)
                tg.send(
                  cid,
                  ('Радар подключён. Новые и изменённые объявления проверяются автоматически. '
                   'Кнопка проверки закреплена внизу чата.') if is_owner else
                  ('Радар подключён. Автоматические уведомления получает владелец бота. '
                   'Вы можете получить актуальную сводку кнопкой ниже.'),
                  reply_keyboard=MAIN_KEYBOARD
                )
                db.set_state(KEYBOARD_STATE,'1')
            elif action=='check':
                force_chats.add(cid)
            elif action=='state':
                show_chats.add(cid)
            elif action=='invite' and cid==str(owner):
                send_invite(db,tg,cid)
        elif 'callback_query' in u:
            q=u['callback_query']; cid=str(q['message']['chat']['id'])
            if cid not in set(subscribed_chat_ids(db)): continue
            tg.answer_callback(q['id'])
            if q.get('data')=='check_now': force_chats.add(cid)
            if q.get('data') in {'state_now','violations'}: show_chats.add(cid)
    db.set_state('telegram_offset',str(offset))
    return force_chats,show_chats,joined_chats

def summary_rows(db):
    return db.query(
      '''SELECT e.*, k.profile_id, k.url, k.address, k.area, k.rooms, k.floor,
                k.raw_json AS kufar_raw_json,
                b.building_name, b.official_address, b.unit_no,
                b.raw_json AS bir_raw_json
         FROM events e
         JOIN kufar_ads k ON k.ad_id=e.ad_id
         LEFT JOIN bir_objects b ON b.object_key=e.object_key
         WHERE e.active=1 AND k.active=1 AND e.occurred_at>=?
           AND e.field_name IN ('price','area')
         ORDER BY e.occurred_at DESC''',
      [settings.live_cutoff_utc]
    )

def service_event_counts(db):
    rows=db.query(
      '''SELECT e.field_name,COUNT(*) AS n
         FROM events e
         JOIN kufar_ads k ON k.ad_id=e.ad_id
         WHERE e.active=1 AND k.active=1 AND e.occurred_at>=?
           AND e.field_name NOT IN ('price','area')
         GROUP BY e.field_name ORDER BY e.field_name''',
      [settings.live_cutoff_utc]
    )
    return {row['field_name']:int(row['n']) for row in rows}

def summary_card(r,bir_checked_at=None):
    field=r.get('field_name')
    probable=probable_event(r)
    building=card_house_label(r)
    address=r.get('address') or r.get('official_address')
    parts=[
      f"{'🟡' if field=='review' else ('🟠' if probable else '🔴')} **{display_card_title(field,probable)}**",'',
      f"👤 **{profile_label(r.get('profile_id'))}**"
    ]
    parts += object_identity_lines(
      building,address,r.get('unit_no'),r.get('rooms'),r.get('area'),r.get('floor'),
      omit_fields={field}
    )
    parts.append('')
    parts += comparison_lines(r)

    kufar_time=fmt_short_dt_minsk((kufar_raw_from_row(r) or {}).get('list_time'))
    detected_time=fmt_short_dt_minsk(r.get('occurred_at'))
    bir_time=fmt_short_dt_minsk(bir_checked_at)
    times=[]
    if kufar_time: times.append(f"Kufar {kufar_time}")
    if detected_time: times.append(f"радар {detected_time}")
    if bir_time: times.append(f"BIR {bir_time}")
    if times: parts += ['',"🕒 "+" · ".join(times)]
    return '\n'.join(parts)

def summary_line(r,bir_checked_at=None):
    return summary_card(r,bir_checked_at)

def summary_link_keyboard(r):
    bir_url=bir_link_from_row(r) if r.get('object_key') else settings.bir_search_url
    return link_keyboard(r.get('url'),bir_url)

def summary_overview(rows,bir_checked_at=None,mode='status',local_now=None,service_counts=None):
    now=local_now or datetime.now(MINSK)
    service_counts=dict(service_counts or {})
    for row in rows:
        field=row.get('field_name')
        if field not in ACTIONABLE_FIELDS:
            service_counts[field]=service_counts.get(field,0)+1
    rows=[row for row in rows if row.get('field_name') in ACTIONABLE_FIELDS]
    title='☀️ **УТРЕННЯЯ ПРОВЕРКА' if mode=='morning' else '🔎 **ПРОВЕРКА ОБЪЯВЛЕНИЙ'
    parts=[f"{title} — {now.strftime('%d.%m')}**",'']
    if not rows:
        parts.append('✅ **Нарушений цены и площади не обнаружено**')
    else:
        parts.append(f"⚠️ **Найдено нарушений цены и площади: {len(rows)}**")
        counts={}
        for r in rows:
            field=r.get('field_name')
            counts[field]=counts.get(field,0)+1
        parts.append('')
        for field in ['price','area']:
            if counts.get(field):
                parts.append(f"{FIELD_ICONS.get(field,'⚠️')} {FIELD_LABELS.get(field,field)} — {counts[field]}")
        people={}
        for r in rows:
            profile_id=r.get('profile_id')
            if profile_id:
                people[profile_id]=people.get(profile_id,0)+1
        if people:
            parts.append('')
            for profile_id,count in people.items():
                parts.append(f"👤 {profile_label(profile_id)} — {count}")
    service_total=sum(service_counts.values())
    if service_total:
        labels={'address':'адрес','floor':'этаж','rooms':'комнаты','existence':'наличие','review':'сопоставление'}
        details=[
          f"{labels.get(field,field)} {service_counts[field]}"
          for field in SERVICE_FIELDS if service_counts.get(field)
        ]
        parts += [
          '',
          f"ℹ️ **Служебные сигналы — {service_total}** (без отдельных уведомлений)",
          ' · '.join(details),
        ]
    checked=parse_any_ts(bir_checked_at)
    if checked:
        parts += ['',f"Проверка завершена в {checked.astimezone(MINSK).strftime('%H:%M')}"]
    return '\n'.join(parts)

def send_state_summary(db,tg,chat,keyboard=True,mode='status'):
    rows=summary_rows(db)
    service_counts=service_event_counts(db)
    bir_checked_at=db.get_state('last_bir_success')
    tg.send(
      chat,telegram_html(summary_overview(
        rows,bir_checked_at,mode=mode,service_counts=service_counts
      )),
      parse_mode='HTML',reply_keyboard=MAIN_KEYBOARD if keyboard else None
    )
    for r in rows:
        tg.send(
          chat,telegram_html(summary_card(r,bir_checked_at)),
          keyboard=summary_link_keyboard(r),parse_mode='HTML'
        )
    if keyboard: db.set_state(KEYBOARD_STATE,'1')

def safe_state_summary(db,tg,chat,keyboard=True,mode='status'):
    try:
        send_state_summary(db,tg,chat,keyboard=keyboard,mode=mode)
        return True
    except Exception as exc:
        print(f'TELEGRAM_SEND_ERROR chat={chat} type={type(exc).__name__} detail={exc}')
        return False

def safe_send(tg,chat,text,**kwargs):
    try:
        tg.send(chat,text,**kwargs)
        return True
    except Exception as exc:
        print(f'TELEGRAM_SEND_ERROR chat={chat} type={type(exc).__name__} detail={exc}')
        return False

def should_live_notify(local_now):
    return 8 <= local_now.hour < 21

def should_send_morning_summary(db,local_now):
    if not (8 <= local_now.hour < 9): return False
    today=local_now.date().isoformat()
    return db.get_state('morning_summary_date','') != today

async def run():
    db=D1(); tg=Telegram()
    force_chats,show_chats,joined_chats=process_updates(db,tg)
    auto_chats=automatic_chat_ids(db)
    owner=db.get_state('telegram_chat_id')
    install_keyboard=bool(auto_chats and db.get_state(KEYBOARD_STATE,'')!='1')

    if owner and db.get_state(INVITE_NOTICE_STATE,'')!='1':
        try:
            send_invite(db,tg,str(owner))
            db.set_state(INVITE_NOTICE_STATE,'1')
        except Exception as exc:
            print(f'TELEGRAM_INVITE_ERROR type={type(exc).__name__} detail={exc}')

    bir_changed=await collect_bir(db,force=bool(force_chats))
    pending=load_pending_audits(db)
    cleaned_polluted_pending=cleanup_polluted_strict_backfill(db,pending)
    profile_runs=[]; targets=[]; all_items=[]
    for profile in KUFAR_PROFILES:
        items,changed,previous_active=await collect_kufar(db,profile)
        all_items.extend(items)
        selected,selection_mode=choose_audit_targets(
          items,changed,previous_active,
          audit_today_on_baseline=profile.get('audit_today_on_baseline',False),
          local_now=datetime.now(MINSK)
        )
        enqueue_pending_audits(pending,selected)
        targets.extend(selected)
        profile_runs.append({
          'id':profile['id'],'label':profile['label'],'items':len(items),
          'changed':len(changed),'previous_active':previous_active,
          'targets':len(selected),'mode':selection_mode,
        })
    # Persist before auditing: if the run is interrupted, no detected change is lost.
    save_pending_audits(db,pending)

    targets=include_active_event_targets(all_items,targets,set(pending))
    today_ids=set()
    strict_recheck=db.get_state(STRICT_ADDRESS_RECHECK_STATE,'')!='1'
    if force_chats or strict_recheck:
        today_ids=reliable_today_version_ad_ids(db,datetime.now(MINSK))
        enqueue_pending_audits(
          pending,[item for item in all_items if item.ad_id in today_ids],
          reason='manual_today' if force_chats else 'strict_address_recheck'
        )
        save_pending_audits(db,pending)
        targets=include_active_event_targets(all_items,targets,today_ids)
    archived_legacy_events=archive_legacy_events_once(db)
    close_inactive_ad_events(db)
    rounded_area_events_closed=close_rounded_area_events(db)
    rechecked_active_events=0
    if bir_changed:
        active_rows=db.query(
          'SELECT DISTINCT ad_id FROM events WHERE active=1 AND occurred_at>=?',
          [settings.live_cutoff_utc]
        )
        before=len(targets)
        targets=include_active_event_targets(
          all_items,targets,{row['ad_id'] for row in active_rows}
        )
        rechecked_active_events=len(targets)-before
        enqueue_pending_audits(pending,targets[before:],reason='bir_update')
        save_pending_audits(db,pending)
    if len(targets)>AUDIT_BATCH_LIMIT:
        targets=targets[:AUDIT_BATCH_LIMIT]
    print(
      f"RADAR_INPUT bir_refreshed={bir_changed} profiles={profile_runs} targets={len(targets)} "
      f"archived_legacy_events={archived_legacy_events} "
      f"rounded_area_events_closed={rounded_area_events_closed} "
      f"rechecked_active_events={rechecked_active_events} "
      f"cleaned_polluted_pending={cleaned_polluted_pending} "
    )

    # Existing profiles audit only incremental NEW/EDITED/REAPPEARED cards.
    # A newly added profile seeds old history silently but still audits rows
    # whose Kufar publication/update time is today in Minsk.
    session=AuditSession(db,[item.ad_id for item in targets])
    all_new=[]
    for k in targets:
        r=session.audit(k)
        for e in session.sync(k,r):
            all_new.append((e,k))
        if r.get('status')=='INSUFFICIENT':
            if k.ad_id in pending:
                pending[k.ad_id]['attempts']=int(pending[k.ad_id].get('attempts') or 0)+1
        else:
            pending.pop(k.ad_id,None)
    statements=session.flush()
    save_pending_audits(db,pending)
    if strict_recheck:
        db.set_state(STRICT_ADDRESS_RECHECK_STATE,'1')
    active_by_field=active_event_counts(db)
    active_by_type=active_event_type_counts(db)
    actionable_new_count=sum(
      1 for event,_item in all_new
      if event.get('field_name') in ACTIONABLE_FIELDS
    )
    actionable_active_count=sum(
      active_by_field.get(field,0) for field in ACTIONABLE_FIELDS
    )
    print(
      f"RADAR_RESULT targets={len(targets)} new_events={len(all_new)} "
      f"actionable_new={actionable_new_count} service_new={len(all_new)-actionable_new_count} "
      f"active_events={sum(active_by_field.values())} actionable_active={actionable_active_count} "
      f"service_active={sum(active_by_field.values())-actionable_active_count} "
      f"active_by_field={active_by_field} active_by_type={active_by_type} statements={statements}"
    )

    local_now=datetime.now(MINSK)
    morning=False
    if auto_chats and should_send_morning_summary(db,local_now):
        sent=False
        for chat in auto_chats:
            sent=safe_state_summary(db,tg,chat,keyboard=True,mode='morning') or sent
        if sent:
            db.set_state('morning_summary_date',local_now.date().isoformat())
            morning=True

    if auto_chats and should_live_notify(local_now) and not morning:
        actionable_new=actionable_event_records(all_new)
        mass,single_records=split_mass_records(actionable_new)
        for field,profile_id,records in mass:
            for chat in auto_chats:
                safe_send(
                  tg,chat,telegram_html(fmt_mass_event_group(field,profile_id,records)),
                  parse_mode='HTML'
                )
        grouped={}
        for e,k in single_records:
            grouped.setdefault(k.ad_id,{'k':k,'events':[]})['events'].append(e)
        for item in grouped.values():
            for chat in auto_chats:
                safe_send(
                  tg,chat,telegram_html(fmt_event_group(db,item['events'],item['k'])),
                  keyboard=event_link_keyboard(db,item['events'][0],item['k']),parse_mode='HTML'
                )

    for chat in show_chats-force_chats:
        safe_state_summary(db,tg,chat,keyboard=True)

    for chat in force_chats|joined_chats:
        safe_state_summary(db,tg,chat,keyboard=True)

    if auto_chats and install_keyboard and not morning and not force_chats and not show_chats and not joined_chats:
        restored=False
        for chat in auto_chats:
            restored=safe_send(
              tg,chat,
              '🔄 Кнопка «Проверить сейчас» снова закреплена внизу чата.',
              reply_keyboard=MAIN_KEYBOARD
            ) or restored
        if restored:
            db.set_state(KEYBOARD_STATE,'1')

if __name__=='__main__':
    asyncio.run(run())
