"""Per-chat Telegram navigation, independent of collection success."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

CURRENT_BUTTON='📋 Актуальные нарушения'
MAIN_KEYBOARD=[[CURRENT_BUTTON]]
NAV_STATE_PREFIX='telegram_navigation_v1_'

def ensure_navigation(db,tg,chat_id,*,now=None,force=False):
    chat=str(chat_id)
    now=now or datetime.now(ZoneInfo('Europe/Minsk'))
    now=now.astimezone(ZoneInfo('Europe/Minsk'))
    today=now.date().isoformat()
    key=NAV_STATE_PREFIX+chat
    try:state=json.loads(db.get_state(key,'{}') or '{}')
    except (TypeError,ValueError):state={}
    if not isinstance(state,dict):state={}
    # Each subscriber has independent success/retry state. A successful send
    # to the owner must never suppress repair of the sister's keyboard.
    if not state.get('menu_configured'):
        try:
            tg.configure_navigation(chat)
            state['menu_configured']=True
            db.set_state(key,json.dumps(state,separators=(',',':')))
        except Exception as exc:
            print(f'TELEGRAM_NAV_MENU_ERROR type={type(exc).__name__}')
    if force or (8<=now.hour<22 and state.get('keyboard_date')!=today):
        try:
            response=tg.send(chat,
              '📋 Панель радара\n'
              '«Актуальные нарушения» — кнопка под строкой ввода. '
              'Она также доступна через «Меню» → «Актуальные нарушения».',
              reply_keyboard=MAIN_KEYBOARD)
            if not (response or {}).get('ok'):raise RuntimeError('Keyboard delivery was not confirmed')
            state['keyboard_date']=today
            state['message_id']=response.get('result',{}).get('message_id')
            db.set_state(key,json.dumps(state,separators=(',',':')))
        except Exception as exc:
            print(f'TELEGRAM_NAV_KEYBOARD_ERROR type={type(exc).__name__}')
            return False
    return bool(state.get('menu_configured') and state.get('keyboard_date'))
