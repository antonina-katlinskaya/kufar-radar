"""Owner-only pinned test panel. Never consumes updates or edits Kufar state."""
import json
import os
from pathlib import Path

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


def format_card(item, bir_checked_at):
    import html
    esc=lambda v: html.escape(str(v if v is not None and v != '' else '—'))
    options=item.get('bir_room_area_candidates') or []
    heading='🟠 <b>ВЕРОЯТНО: НЕСОВПАДЕНИЕ С BIR</b>'
    lines=[heading,'',f"👤 <b>{esc(item['person'])}</b>"]
    if item.get('address'): lines.append(f"📍 {esc(item['address'])}")
    lines += [f"🚪 {esc(item.get('rooms'))} комн. · {esc(item.get('area'))} м² · {esc(item.get('floor'))} этаж",
              '',f"<b>Realt: {esc(item.get('price'))} {('€' if str(item.get('currency')) in ('978','EUR') else esc(item.get('currency')))}</b>"]
    if options:
        specials=sorted({str(x.get('special_price_eur')) for x in options if x.get('special_price_eur') is not None})
        lines.append('<b>BIR, спеццена: '+esc(', '.join(specials) or '—')+' €</b>')
    else:
        lines.append('<b>BIR: объект с теми же комнатами и точной площадью не найден</b>')
    lines += ['',f"⚠️ {esc(item.get('reason'))}",'',f"🕒 BIR: {esc(bir_checked_at)}",
              '<i>Предварительное расхождение; требуется проверка.</i>']
    return '\\n'.join(lines)


def publish(result, owner, bot, run_url, review_items=None):
    chat=bot.call('getChat', {'chat_id': OWNER_ID})
    target=validate_owner(owner,chat)
    selected=review_items if review_items is not None else result.get('items',[])
    if not selected or not result.get('bir_checked_at'):
        raise RuntimeError('Refusing to send an empty or unchecked report')
    receipt={'notification_sent':False,'owner_verified':True,'message_ids':[],
             'delivered_items':[],'documents_sent':[],'run_url':run_url}
    for item in selected:
        if item.get('status')!='REVIEW': continue
        url=item.get('url')
        buttons=[[{'text':'Открыть Realt','url':url}]] if url and url.startswith('https://realt.by/') else []
        message=bot.call('sendMessage', {'chat_id':target,
            'text':format_card(item,result['bir_checked_at']),
            'parse_mode':'HTML','disable_web_page_preview':True,
            'reply_markup':{'inline_keyboard':buttons}})
        receipt['message_ids'].append(message['message_id'])
        receipt['delivered_items'].append(item)
        receipt['notification_sent']=True
        Path('realt_test/notification_receipt.json').write_text(
            json.dumps({k:v for k,v in receipt.items() if k!='delivered_items'},ensure_ascii=False,indent=2),encoding='utf-8')
    return receipt


def main():
    permitted = (os.getenv('GITHUB_REF') == 'refs/heads/' + BRANCH or (os.getenv('GITHUB_REF') == 'refs/heads/main' and os.getenv('GITHUB_WORKFLOW') == 'Realt scheduled owner-only'))
    if not permitted or os.getenv('GITHUB_REPOSITORY') != REPOSITORY:
        raise RuntimeError('Telegram test is restricted to the explicitly authorized branch')
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        raise RuntimeError('Telegram token is missing; no message sent')
    from radar.d1 import D1
    # This is the only production read. No writes, subscribers, polling or shared menu.
    owner = D1().get_state('telegram_chat_id')
    if str(owner) != OWNER_ID:
        raise RuntimeError('Owner state changed; no message sent')
    result = json.loads(Path('realt_test/results.json').read_text(encoding='utf-8'))
    from realt_test.history import pending, acknowledge
    history_db = D1()
    unsent, _ = pending(history_db, result)
    if not unsent:
        print(json.dumps({'notification_sent': False, 'pending_reviews': 0, 'reason': 'No new or changed review cases'}))
        return
    run_url = f"https://github.com/{REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    from collections import Counter
    from realt_test.run import write_reports
    selected_counts = {person: dict(Counter(x['status'] for x in unsent if x['person'] == person))
                       for person in result['tracked_people']}
    delivery_result = {**result, 'items': unsent, 'checked': len(unsent),
                       'status_counts': dict(Counter(x['status'] for x in unsent)),
                       'person_status_counts': selected_counts}
    write_reports(delivery_result)
    receipt = publish(delivery_result, owner, Bot(token), run_url, review_items=unsent)
    if receipt['delivered_items']:
        acknowledge(history_db, receipt['delivered_items'])
    print(json.dumps({k:v for k,v in receipt.items() if k!='delivered_items'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
