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


def publish(result, owner, bot, run_url):
    chat = bot.call('getChat', {'chat_id': OWNER_ID})
    target = validate_owner(owner, chat)
    if not result.get('items') or not result.get('bir_checked_at'):
        raise RuntimeError('Refusing to send an empty or unchecked report')
    text = ['🧪 Realt — тест', '', 'Объявления, созданные 23–26 октября 2026 включительно.',
            f"Проверено: {result['checked']}. Совпали: {result['status_counts'].get('OK', 0)}. Требуют проверки: {result['status_counts'].get('REVIEW', 0)}.", '']
    for person, counts in result['person_status_counts'].items():
        text.append(f"{person}: {sum(counts.values())}; совпали {counts.get('OK', 0)}, проверить {counts.get('REVIEW', 0)}")
    text += ['', f"Снимок Bir: {result['bir_checked_at']}", '',
             'Сравниваются комнаты, точная площадь без округления и специальная стоимость при быстрой оплате. Этаж не входит в первичный фильтр.',
             '', result['coverage_warning'], '', 'Подробный отчёт и список объявлений приложены к этому сообщению.']
    message = bot.call('sendMessage', {
        'chat_id': target, 'text': '\n'.join(text), 'disable_web_page_preview': True,
        'reply_markup': {'inline_keyboard': [
            [{'text': 'Результаты этой проверки', 'url': run_url}],
            [{'text': 'История Realt — тест', 'url': f'https://github.com/{REPOSITORY}/actions?query=branch%3A{BRANCH}+workflow%3A%22Realt+private+test%22'}],
        ]},
    })
    receipt = {'notification_sent': True, 'owner_verified': True, 'message_id': message['message_id'],
               'pinned': False, 'documents_sent': [], 'run_url': run_url}
    receipt_path = Path('realt_test/notification_receipt.json')
    def save():
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    receipt['pinned'] = bool(bot.call('pinChatMessage', {
        'chat_id': target, 'message_id': message['message_id'], 'disable_notification': True}))
    save()
    result['notification_sent'] = True
    Path('realt_test/results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    for name in ('results.csv', 'results.md', 'results.json'):
        with open('realt_test/' + name, 'rb') as f:
            bot.call('sendDocument', {'chat_id': target, 'caption': 'Realt — тест · ' + name,
                     'reply_parameters': json.dumps({'message_id': message['message_id']})},
                     files={'document': (name, f)})
        receipt['documents_sent'].append(name)
        save()
    return receipt


def main():
    if os.getenv('GITHUB_REF') != 'refs/heads/' + BRANCH or os.getenv('GITHUB_REPOSITORY') != REPOSITORY:
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
    run_url = f"https://github.com/{REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    receipt = publish(result, owner, Bot(token), run_url)
    result['notification_sent'] = receipt['notification_sent']
    Path('realt_test/results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
