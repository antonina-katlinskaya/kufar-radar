"""Owner-only technical delivery, independent of D1 and the BIR Telegram bot."""
import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

OWNER = '352252956'
REPO = 'antonina-katlinskaya/kufar-radar'
BRANCH = 'realt-state'
STATE_PATH = 'technical_monitor/state.json'


def daytime(now):
    return 8 <= now.astimezone(ZoneInfo('Europe/Minsk')).hour < 22


def pipeline_problem(env, detail):
    if env.get('BIR_REFRESH_OUTCOME') == 'failure':
        if 7500 in detail.get('codes', []):
            return ('bir_database', 'Бесплатная дневная квота чтения базы Bir исчерпана. '
                    'Сверка объявлений Kufar и Realt со свежими данными Bir приостановлена. '
                    'Квота обновляется в 03:00 по Минску. Платные услуги не подключены.')
        return ('bir_database', 'Не удалось обновить базу Bir для сверки объявлений. '
                'Проверка цен и комнатности Kufar приостановлена до успешного обновления. '
                'Это технический сбой, а не нарушение сотрудника.')
    if env.get('KUFAR_BRIDGE_OUTCOME') == 'failure':
        return ('kufar_source', 'Не удалось загрузить объявления Kufar для сверки с Bir. '
                'Новые нарушения пока не проверены.')
    if env.get('RADAR_SCAN_OUTCOME') == 'failure':
        return ('radar', 'Сверка Kufar или отправка уведомлений не завершилась. '
                'Отсутствие сообщений сейчас не подтверждает отсутствие нарушений.')
    return None


def api(url, body=None, token=None, method=None, missing=False):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'radar-technical-monitor'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = None if body is None else json.dumps(body).encode()
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if missing and exc.code == 404:
            return None
        raise RuntimeError('Remote request failed, HTTP ' + str(exc.code)) from None
    except Exception:
        # Never expose Telegram URLs, which contain a bot credential.
        raise RuntimeError('Remote request failed; credential-bearing URL suppressed') from None


class Store:
    def __init__(self):
        self.url = f'https://api.github.com/repos/{REPO}/contents/{STATE_PATH}'
        self.token = os.environ['GITHUB_TOKEN']
        remote = api(self.url + '?ref=' + BRANCH, token=self.token, missing=True)
        self.sha = remote['sha'] if remote else None
        self.data = json.loads(base64.b64decode(remote['content'])) if remote else {'schema': 1, 'incidents': {}}
        if self.data.get('schema') != 1 or not isinstance(self.data.get('incidents'), dict):
            raise RuntimeError('Invalid isolated technical-notification state')

    def save(self):
        payload = {'message': 'radar: persist technical notification receipt [skip ci]',
                   'branch': BRANCH,
                   'content': base64.b64encode(json.dumps(self.data, ensure_ascii=False).encode()).decode()}
        if self.sha:
            payload['sha'] = self.sha
        response = api(self.url, payload, self.token, 'PUT')
        self.sha = response['content']['sha']


def send(text):
    token = os.environ['TELEGRAM_BOT_TOKEN']
    root = 'https://api.telegram.org/bot' + token + '/'
    me = api(root + 'getMe', {})
    chat = api(root + 'getChat', {'chat_id': OWNER})
    if not me.get('ok') or not chat.get('ok'):
        raise RuntimeError('Telegram bot or recipient verification failed')
    target = chat['result']
    if str(target.get('id')) != OWNER or target.get('type') != 'private':
        raise RuntimeError('Refusing an unverified technical recipient')
    response = api(root + 'sendMessage', {'chat_id': OWNER, 'text': text, 'disable_web_page_preview': True})
    if not response.get('ok'):
        raise RuntimeError('Telegram did not confirm technical delivery')
    receipt = {'message_id': response['result']['message_id'], 'chat_id': OWNER,
               'bot_username': me['result'].get('username'), 'bot_name': me['result'].get('first_name')}
    print(json.dumps({'technical_delivery': receipt}, ensure_ascii=False))
    return receipt


def main():
    if os.getenv('GITHUB_REPOSITORY') != REPO or os.getenv('GITHUB_REF') != 'refs/heads/main':
        raise RuntimeError('Technical notifier is restricted to the production repository and branch')
    now = datetime.now(timezone.utc)
    store = Store()
    detail_path = Path(os.getenv('BIR_FAILURE_REASON_PATH', '/tmp/bir-refresh-failure.json'))
    detail = json.loads(detail_path.read_text()) if detail_path.exists() else {}
    problem = pipeline_problem(os.environ, detail)
    url = f"https://github.com/{REPO}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    if not store.data.get('setup_receipt') and daytime(now):
        # Claim before the external side effect: a crashed run never blindly repeats it.
        if not store.data.get('setup_claim'):
            store.data['setup_claim'] = now.isoformat()
            store.save()
            receipt = send('🔧 Проверка технического канала «Куфр радар нарушения».\n'
                           'Технические ошибки сверки Bir/Kufar направляются только вам. '
                           'Уведомления о нарушениях сотрудников предназначены сестре. '
                           'Это проверочное сообщение, не сообщение об успешной публикации.')
            store.data['setup_receipt'] = receipt
            store.save()
    incidents = store.data['incidents']
    if problem:
        key, explanation = problem
        previous = incidents.get(key, {})
        previous['active'] = True
        previous['text'] = explanation
        previous['run_url'] = url
        last = previous.get('claimed_at')
        due = not last or (now - datetime.fromisoformat(last)).total_seconds() >= 4 * 3600
        incidents[key] = previous
        if daytime(now) and due:
            previous['claimed_at'] = now.isoformat()
            store.save()
            previous['receipt'] = send('⚠️ Техническая проблема радара\n' + explanation + '\nЖурнал: ' + url)
            store.save()
        elif not last:
            # Quiet-hour failures are retained for the next daytime run.
            store.save()
    else:
        changed = False
        for incident in incidents.values():
            if incident.get('active'):
                incident['active'] = False
                incident['recovered_at'] = now.isoformat()
                changed = True
        if changed:
            store.save()
    print(json.dumps({'checked': True, 'problem': problem[0] if problem else None,
                      'delivery_window_open': daytime(now), 'uses_d1_for_delivery': False}))


if __name__ == '__main__':
    main()
