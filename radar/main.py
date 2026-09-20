import asyncio, json, os, tempfile
from datetime import datetime, timezone, timedelta
from .config import settings
from .d1 import D1
from .telegram import Telegram
from .collectors.kufar import KufarCollector, screenshot_ad
from .collectors.bir import BirCollector
from .store import save_kufar, save_bir, current_kufar
from .audit import audit_one, sync_events

KEYBOARD=[[{'text':'🔎 Проверить сейчас','callback_data':'check_now'}],[{'text':'🚨 Нарушения сейчас','callback_data':'violations'}]]

def fmt_event(e,k=None):
    names={'price':'цена','area':'площадь','rooms':'комнаты','floor':'этаж','address':'адрес','existence':'актуальность объекта'}
    icon='✅' if e['event_type']=='RESTORED' else '🚨'
    title={'NEW_MISMATCH':'Новое расхождение','REPEAT':'Повторное расхождение','RESTORED':'Исправлено','STALE':'Объект исчез с Bir','NO_BIR_OBJECT':'Объект не найден на Bir'}.get(e['event_type'],e['event_type'])
    s=f"{icon} {title}\nID: {e['ad_id']}\nПоле: {names.get(e['field_name'],e['field_name'])}"
    if e.get('new_value') is not None: s+=f"\nKufar: {e['new_value']}"
    if e.get('bir_value') is not None: s+=f"\nBir: {e['bir_value']}"
    if k and k.url: s+=f"\n{k.url}"
    return s

def save_diag(db,source,diag):
    ts=datetime.now(timezone.utc).isoformat(); stm=[]
    seen=set()
    for url,method,status,ct in diag[-100:]:
        key=(url,method,status,ct)
        if key in seen: continue
        seen.add(key); stm.append(('INSERT INTO source_diagnostics(source,observed_at,url,method,status,content_type,note) VALUES(?,?,?,?,?,?,?)',[source,ts,url,method,status,ct,None]))
    if stm: db.batch(stm)

def parse_ts(v):
    try: return datetime.fromisoformat(v.replace('Z','+00:00'))
    except: return None

async def collect_bir(db,force=False):
    last=db.get_state('last_bir_success')
    if not force and last:
        dt=parse_ts(last)
        if dt and datetime.now(timezone.utc)-dt < timedelta(minutes=settings.bir_refresh_minutes): return False
    c=BirCollector(); items=await c.collect(); save_diag(db,'bir',c.diagnostics); save_bir(db,items)
    db.set_state('last_bir_success',datetime.now(timezone.utc).isoformat()); db.set_state('last_bir_count',str(len(items)))
    return True

async def collect_kufar(db):
    c=KufarCollector(); items=await c.collect(); save_diag(db,'kufar',c.diagnostics); changed=save_kufar(db,items,settings.kufar_profile_id)
    db.set_state('last_kufar_success',datetime.now(timezone.utc).isoformat()); db.set_state('last_kufar_count',str(len(items)))
    return items,changed

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
                tg.send(cid,'Радар подключён. Проверка идёт каждые 5 минут.',KEYBOARD)
            elif txt.startswith('/check'): force=True
            elif txt.startswith('/violations'): show=True
        elif 'callback_query' in u:
            q=u['callback_query']; cid=str(q['message']['chat']['id']); allowed=db.get_state('telegram_chat_id')
            if cid!=allowed: continue
            tg.answer_callback(q['id'])
            if q.get('data')=='check_now': force=True
            if q.get('data')=='violations': show=True
    db.set_state('telegram_offset',str(offset))
    return force,show

def show_violations(db,tg,chat):
    rows=db.query('SELECT e.*, k.url FROM events e LEFT JOIN kufar_ads k ON k.ad_id=e.ad_id WHERE e.active=1 ORDER BY e.occurred_at DESC LIMIT 40')
    if not rows: tg.send(chat,'Сейчас активных расхождений не зафиксировано.',KEYBOARD); return
    parts=[f"🚨 Активных расхождений: {len(rows)}"]
    for r in rows[:25]: parts.append(f"• {r['ad_id']} — {r['field_name']}: {r.get('new_value')} / Bir {r.get('bir_value')}")
    tg.send(chat,'\n'.join(parts),KEYBOARD)

async def run():
    db=D1(); tg=Telegram(); force,show=process_updates(db,tg); chat=db.get_state('telegram_chat_id')
    if show and chat: show_violations(db,tg,chat)
    bir_changed=await collect_bir(db,force=force)
    items,changed=await collect_kufar(db)
    targets=current_kufar(db,settings.kufar_profile_id) if (force or bir_changed) else changed
    all_new=[]
    for k in targets:
        r=audit_one(db,k); evs=sync_events(db,k,r)
        for e in evs: all_new.append((e,k))
    if chat:
        for e,k in all_new:
            tg.send(chat,fmt_event(e,k),KEYBOARD)
            if settings.send_screenshots and e['event_type'] in {'NEW_MISMATCH','REPEAT','STALE','NO_BIR_OBJECT'} and k.url:
                path=os.path.join(tempfile.gettempdir(),f"kufar_{k.ad_id}.png")
                if await screenshot_ad(k.url,path):
                    try: tg.photo(chat,path,f"Фиксация Kufar {k.ad_id}")
                    except: pass
        if force:
            active=db.query('SELECT COUNT(*) AS n FROM events WHERE active=1')[0]['n']
            tg.send(chat,f"✅ Полная проверка завершена. Активных объявлений: {len(items)}. Активных расхождений: {active}.",KEYBOARD)

if __name__=='__main__': asyncio.run(run())
