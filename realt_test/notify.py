"""Owner-only pinned test panel. Never consumes updates or edits Kufar state."""
import json
import os
from pathlib import Path

SISTER_ID = '1037292158'  # Verified active Kufar subscriber.
OWNER_ID = '352252956'  # Existing authoritative telegram_chat_id, verified 2026-10-26.
BRANCH = 'realt-private-test-20261026'
REPOSITORY = 'antonina-katlinskaya/kufar-radar'


def validate_owner(owner, chat):
    if str(owner) != OWNER_ID or str(chat.get('id')) != OWNER_ID or chat.get('type') != 'private':
        raise RuntimeError('Private test owner verification failed; nothing sent')
    return OWNER_ID


class Bot:
    def __init__(self, token):
        import httpx
        self.client = httpx.Client(timeout=60)
        self.base = 'https://api.telegram.org/bot' + token

    def call(self, method, payload, files=None):
        try:
            if files:
                response = self.client.post(self.base + '/' + method, data=payload, files=files)
            else:
                response = self.client.post(self.base + '/' + method, json=payload)
            result = response.json()
            if not response.is_success or not result.get('ok'):
                raise ValueError('Bot API rejected call')
            return result['result']
        except Exception:
            # httpx exceptions can contain the bot token in their request URL.
            raise RuntimeError(f'Telegram {method} failed; token and request URL suppressed') from None


def validate_sister(recipient,chat):
    if str(recipient)!=SISTER_ID or str(chat.get('id'))!=SISTER_ID or chat.get('type')!='private':
        raise RuntimeError('Sister recipient verification failed')
    return SISTER_ID


def format_card(item, bir_checked_at):
    """Same visual hierarchy as Kufar cards; do not claim an unverified violation."""
    import html
    from datetime import datetime
    from zoneinfo import ZoneInfo
    esc = lambda value: html.escape(str(value if value is not None and value != '' else '—'))
    options = item.get('bir_room_area_candidates') or []
    def number(value, digits=2):
        try:
            return f"{float(value):,.{digits}f}".replace(",", " ").replace(".", ",")
        except (ValueError, TypeError):
            return esc(value)
    def date(value):
        try:
            dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return dt.astimezone(ZoneInfo('Europe/Minsk')).strftime('%d.%m %H:%M') if dt.tzinfo else dt.strftime('%d.%m %H:%M')
        except (ValueError, TypeError):
            return None
    price = number(item.get('price'), 0)
    currency = {'978':'€','EUR':'€','933':'BYN','BYN':'BYN'}.get(str(item.get('currency')), 'валюта неизвестна')
    lines = ['⚠️ <b>ЗАДНИМ ЧИСЛОМ ИЗМЕНЕНЫ СУЩЕСТВЕННЫЕ ПАРАМЕТРЫ</b>' if item.get('status') == 'BACKDATED' else '🟠 <b>ВЕРОЯТНО: НЕТ СОВПАДЕНИЯ КОМНАТ + ПЛОЩАДИ + СПЕЦЦЕНЫ</b>',
             '', f"👤 <b>{esc(item.get('person'))}</b>"]
    if item.get('status')=='RESOLVED':
        lines[0]='✅ <b>ПРЕДЫДУЩЕЕ РАСХОЖДЕНИЕ УСТРАНЕНО</b>'
    if item.get('quarter'):
        lines.append(f"🏢 {esc(item['quarter'])}")
    address = str(item.get('address') or '')
    house = str(item.get('house_number') or '').strip()
    if house and house not in address.split(): address = (address + ' ' + house).strip()
    if address: lines.append(f"📍 {esc(address)}")
    specifications = [f"{esc(item.get('rooms'))}-комн.", f"{number(item.get('area'))} м²"]
    if item.get('floor') is not None and item.get('floor') != '':
        specifications.append(f"{esc(item['floor'])} этаж")
    lines += ['🚪 ' + ' · '.join(specifications), '',
              f"<b>Realt: {price} {currency}</b>"]
    if options:
        regulars = sorted({number(x.get('regular_price_eur'), 0) for x in options if x.get('regular_price_eur') is not None})
        specials = sorted({number(x.get('special_price_eur'), 0) for x in options if x.get('special_price_eur') is not None})
        lines.append("<b>BIR: " + (", ".join(regulars) + " €" if regulars else "обычная цена неизвестна") + "</b>")
        lines.append("<b>Спеццена BIR: " + (", ".join(specials) + " €" if specials else "не указана") + "</b>")
        if len(options) > 1:
            lines.append(f"В BIR найдено {len(options)} объектов с такими комнатами и площадью")
    else:
        lines.append("<b>BIR: объект с совпадением комнат и точной площади не найден</b>")
        lines.append("Обычную и специальную цену BIR установить невозможно")
    for edit in item.get('material_edits') or []:
        for change in edit.get('changes') or []:
            lines.append(f"⚠️ {esc(change['field'])}: {esc(change['before'])} → {esc(change['after'])}")
    timestamps = []
    if date(item.get('created_at')):
        timestamps.append('Realt ' + date(item['created_at']))
    if date(item.get('radar_checked_at')):
        timestamps.append('радар ' + date(item['radar_checked_at']))
    if date(bir_checked_at):
        timestamps.append('BIR ' + date(bir_checked_at))
    if timestamps:
        lines += ['', '🕒 ' + ' · '.join(timestamps)]
    lines += ['', '<i>Комнаты, точная площадь и спеццена Bir теперь совпали.</i>' if item.get('status')=='RESOLVED' else '<i>Предварительное расхождение, требуется проверка.</i>']
    return '\n'.join(lines)


def publish(result, owner, bot, run_url, review_items=None, before_send=None, after_send=None, recipient=None):
    recipient=recipient or OWNER_ID
    chat=bot.call('getChat', {'chat_id': recipient})
    target=validate_owner(owner,chat) if recipient==OWNER_ID else validate_sister(recipient,chat)
    selected=review_items if review_items is not None else result.get('items',[])
    if not selected or not result.get('bir_checked_at'):
        raise RuntimeError('Refusing to send an empty or unchecked report')
    receipt={'notification_sent':False,'owner_verified':True,'message_ids':[],
             'delivered_items':[],'documents_sent':[],'run_url':run_url}
    for item in selected:
        if item.get('status') not in ('REVIEW', 'BACKDATED', 'RESOLVED'): continue
        url=item.get('url')
        buttons=[[{'text':'Открыть Realt','url':url}]] if url and url.startswith('https://realt.by/') else []
        import re
        for candidate in (item.get('bir_room_area_candidates') or [])[:3]:
            uid=str(candidate.get('id') or '')
            if re.fullmatch(r'[a-fA-F0-9-]{36}',uid):
                buttons.append([{'text':'Bir: '+str(candidate.get('house') or '')+' · кв. '+str(candidate.get('unit') or ''),'url':'https://bir.by/object/'+uid+'/'}])
        if before_send:before_send(item)
        message=bot.call('sendMessage', {'chat_id':target,
            'text':format_card(item,result['bir_checked_at']),
            'parse_mode':'HTML','disable_web_page_preview':True,
            'reply_markup':{'inline_keyboard':buttons}})
        receipt['message_ids'].append(message['message_id'])
        receipt['delivered_items'].append(item)
        receipt['notification_sent']=True
        if after_send:after_send(item)
        Path('realt_test/notification_receipt.json').write_text(
            json.dumps({k:v for k,v in receipt.items() if k!='delivered_items'},ensure_ascii=False,indent=2),encoding='utf-8')
    return receipt


class SisterHistory:
    from realt_test.history import KEY, CLAIMS_KEY
    KEYS={KEY:'realt_sister_review_fingerprints_v1', CLAIMS_KEY:'realt_sister_delivery_claims_v1'}
    def __init__(self,store):
        self.store=store
        if store.get_state(self.KEYS[self.KEY]) is None:
            store.set_state(self.KEYS[self.KEY],store.get_state(self.KEY) or '{}')
    def get_state(self,key,default=None):
        return self.store.get_state(self.KEYS.get(key,key),default)
    def set_state(self,key,value):
        return self.store.set_state(self.KEYS.get(key,key),value)


def main():
    permitted = (os.getenv('GITHUB_REF') == 'refs/heads/' + BRANCH or (os.getenv('GITHUB_REF') == 'refs/heads/main' and os.getenv('GITHUB_WORKFLOW') == 'Realt scheduled owner-only'))
    if not permitted or os.getenv('GITHUB_REPOSITORY') != REPOSITORY:
        raise RuntimeError('Telegram test is restricted to the explicitly authorized branch')
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        raise RuntimeError('Telegram token is missing; no message sent')
    from realt_test.github_store import GitHubState
    # This is the only production read. No writes, subscribers, polling or shared menu.
    owner = GitHubState().get_state('realt_owner_id')
    if str(owner) != OWNER_ID:
        raise RuntimeError('Owner state changed; no message sent')
    result = json.loads(Path('realt_test/results.json').read_text(encoding='utf-8'))
    if result.get('notification_paused'):
        print(json.dumps({'notification_sent':False,'reason':'Archive baseline restored; waiting for a fresh collector snapshot'}))
        return
    if result.get('budget_paused') is not None:
        budget=result['budget_paused']
        day=result.get('checked_at','')[:10]
        db=GitHubState()
        key='realt_owner_budget_pause_notice_v1'
        if db.get_state(key)!=day:
            bot=Bot(token)
            validate_owner(owner,bot.call('getChat',{'chat_id':OWNER_ID}))
            text=('⏸ Realt Radar: новые сверки временно приостановлены для сохранения бесплатной квоты.\n'
                  + ('Прочитано строк D1: '+str(budget['rows_read'])+' из 5 000 000.\n' if 'rows_read' in budget else '')
                  + str(budget.get('reason') or 'Достигнут защитный порог 80% аккаунта.')
                  + '\nKufar Radar не изменён. Устаревшие данные Bir не используются.')
            sent=bot.call('sendMessage',{'chat_id':OWNER_ID,'text':text})
            db.set_state(key,day)
            Path('realt_test/notification_receipt.json').write_text(json.dumps({'notification_sent':True,'type':'budget_pause','owner_verified':True,'message_ids':[sent['message_id']]},indent=2))
        return
    from realt_test.history import pending, acknowledge, claim
    owner_store=GitHubState()
    sister_store=SisterHistory(owner_store)
    cases=[]
    for label,recipient,store in [('owner',OWNER_ID,owner_store),('sister',SISTER_ID,sister_store)]:
        unsent,_=pending(store,result)
        if unsent:cases.append((label,recipient,store,unsent))
    if not cases:
        print(json.dumps({'notification_sent':False,'reason':'No new cases for either recipient'}))
        return
    from datetime import datetime,timezone,timedelta
    stamp=datetime.fromisoformat(str(result.get('bir_checked_at') or '').replace('Z','+00:00'))
    age=datetime.now(timezone.utc)-stamp
    if age<timedelta(minutes=-5) or age>timedelta(minutes=35):
        raise RuntimeError('Bir snapshot stale; no messages sent')
    run_url=f"https://github.com/{REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    bot=Bot(token)
    receipts={}
    for label,recipient,store,items in cases:
        receipt=publish(result,owner,bot,run_url,review_items=items,recipient=recipient,
            before_send=lambda item,db=store:claim(db,item),
            after_send=lambda item,db=store:acknowledge(db,[item]))
        receipts[label]={k:v for k,v in receipt.items() if k!='delivered_items'}
    print(json.dumps(receipts,ensure_ascii=False))


if __name__ == '__main__':
    main()
