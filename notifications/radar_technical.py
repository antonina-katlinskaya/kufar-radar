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



BIR_HEALTH_URL = 'https://bir-radar-diagnostic.an-katlinskaya.workers.dev/status/public'


def bir_bot_problem(snapshot, now):
    """Use actual source/delivery evidence; planned overnight pauses are normal."""
    local=now.astimezone(ZoneInfo('Europe/Minsk'))
    if snapshot is None:
        return ('bir_bot_unavailable','Не удалось получить состояние Bir-бота. Его работа и доставка сообщений сейчас не подтверждены.')
    if not isinstance(snapshot,dict) or 'ok' not in snapshot or not snapshot.get('now'):
        return ('bir_bot_invalid_health','Bir-бот вернул неполные диагностические данные; работу нельзя подтвердить.')
    try:
        response_time=datetime.fromisoformat(snapshot['now'].replace('Z','+00:00'))
        if abs((now-response_time).total_seconds())>300:
            return ('bir_bot_invalid_health','Диагностический ответ Bir-бота устарел; свежесть работы не подтверждена.')
    except (ValueError,TypeError):
        return ('bir_bot_invalid_health','В диагностике Bir-бота некорректное время ответа.')
    if not (7 <= local.hour < 21):
        # The inventory cron has no planned source scans between 21:00 and 07:00.
        return None
    reason=snapshot.get('reason')
    if reason=='stale':
        try:
            last=datetime.fromisoformat(snapshot['lastSuccessAt'].replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Minsk')).strftime('%d.%m %H:%M (Минск)')
        except (KeyError,ValueError,TypeError):
            last='неизвестно'
        return ('bir_bot_stale','Bir-бот перестал успешно обновлять остатки. Последнее успешное обновление: '
                +last+'. Уведомления о новых квартирах и ценах могут запаздывать.')
    if reason in ('no_v4_baseline','health_unavailable'):
        return ('bir_bot_unavailable','Bir-бот не подтвердил исправное состояние: нет доступных данных мониторинга.')
    if snapshot.get('telegramErrors',0):
        return ('bir_bot_delivery','Bir-бот не смог доставить сообщения подписчице. Очередь сохранена; требуется проверка доставки в Telegram.')
    if snapshot.get('pendingNotifications',0):
        return ('bir_bot_backlog','В Bir-боте накопились неотправленные сообщения: '
                +str(snapshot['pendingNotifications'])+'. Данные собираются, но доставка задерживается.')
    if reason:
        return ('bir_bot_error','Bir-бот сообщил об ошибке сбора или проверки данных ('+str(reason)+'). Свежие результаты не подтверждены.')
    if local.hour>=8 and (local.hour,local.minute)>=(8,20):
        if snapshot.get('lastScheduledDailySnapshotDate')!=local.date().isoformat():
            return ('bir_bot_digest','Bir-бот не сформировал ожидаемую сводку на 08:00 за сегодня. Требуется проверка утреннего задания.')
    return None


def observe_bir(state, problem, now):
    """Require two distinct checks over >=3 minutes before reporting an outage."""
    old=state.get('bir_observation')
    if problem is None:
        if old:
            state.pop('bir_observation',None)
        return None, bool(old)
    key,text=problem
    if not old or old.get('key')!=key:
        state['bir_observation']={'key':key,'first_at':now.isoformat(),'checks':1,'last_at':now.isoformat()}
        return None, True
    elapsed=(now-datetime.fromisoformat(old['last_at'])).total_seconds()
    if elapsed>=180:
        old['checks']=old.get('checks',1)+1
        old['last_at']=now.isoformat()
        return (problem if old['checks']>=2 else None), True
    return None, False


def observe_pipeline(state, problem, now, verified_success=False, quota=False):
    old=state.get('pipeline_observation')
    if problem is None:
        if verified_success and old:
            state.pop('pipeline_observation',None)
            return None, True
        return None, False
    key,text=problem
    if not old or old.get('key')!=key:
        state['pipeline_observation']={'key':key,'first_at':now.isoformat(),'last_at':now.isoformat(),'checks':1}
        return (problem if quota else None), True
    elapsed=(now-datetime.fromisoformat(old['last_at'])).total_seconds()
    if elapsed>=180:
        old['checks']=old.get('checks',1)+1
        old['last_at']=now.isoformat()
        return (problem if quota or old['checks']>=2 else None), True
    return (problem if quota else None), False


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
    pipeline = pipeline_problem(os.environ, detail)
    # Do not report a single transient pipeline failure. Require a second
    # independent run, but report confirmed quota exhaustion immediately.
    pipeline_observed = pipeline
    pipeline_verified = all(os.environ.get(key) == 'success' for key in
                            ('BIR_REFRESH_OUTCOME','KUFAR_BRIDGE_OUTCOME','RADAR_SCAN_OUTCOME'))
    pipeline, pipeline_changed = observe_pipeline(store.data, pipeline, now, pipeline_verified,
                                                  7500 in detail.get('codes', []))
    if pipeline_changed: store.save()
    try:
        snapshot=api(BIR_HEALTH_URL)
    except RuntimeError:
        snapshot=None
    observed=bir_bot_problem(snapshot,now)
    bir_problem,observation_changed=observe_bir(store.data,observed,now)
    if observation_changed: store.save()
    problems=([pipeline] if pipeline else [])+([bir_problem] if bir_problem else [])
    print(json.dumps({'bir_bot_health':{'reachable':snapshot is not None,'reason':observed[0] if observed else None,'lastSuccessAt':snapshot.get('lastSuccessAt') if snapshot else None,'pendingNotifications':snapshot.get('pendingNotifications') if snapshot else None,'telegramErrors':snapshot.get('telegramErrors') if snapshot else None}},ensure_ascii=False))
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
    if snapshot and not observed and not store.data.get('bir_monitor_setup_claim') and daytime(now):
        store.data['bir_monitor_setup_claim']=now.isoformat()
        store.save()
        store.data['bir_monitor_setup_receipt']=send(
            '🔧 Проверка внешнего контроля Bir-бота.\n'
            'Получен свежий ответ работающего сервиса: очередь сообщений пуста, ошибок доставки нет. '
            'Контроль проверяет обновления остатков, очередь Telegram и утреннюю сводку. '
            'Подтверждённые технические проблемы направляются только вам в этот бот; сестре — рабочие уведомления Bir.')
        store.save()
    incidents = store.data['incidents']
    active_keys={key for key,_ in problems}
    # A first failed health check is not a recovery; preserve an existing incident.
    if observed: active_keys.add(observed[0])
    if pipeline_observed: active_keys.add(pipeline_observed[0])
    if not pipeline_verified:
        active_keys.update(k for k in ('bir_database','kufar_source','radar') if incidents.get(k,{}).get('active'))
    changed=False
    for key,incident in incidents.items():
        if key not in active_keys and incident.get('active'):
            incident['active']=False
            incident['recovered_at']=now.isoformat()
            changed=True
    if changed: store.save()
    for key,explanation in problems:
        previous=incidents.get(key,{})
        if not previous.get('active'):
            previous={}
        previous['active']=True
        previous['text']=explanation
        previous['run_url']=url
        last=previous.get('claimed_at')
        due=not last  # One notification per incident; no periodic repeats.
        incidents[key]=previous
        if daytime(now) and due:
            previous['claimed_at']=now.isoformat()
            store.save()
            previous['receipt']=send('⚠️ Техническая проблема радара\n'+explanation+'\nЖурнал: '+url)
            store.save()
        elif not last:
            store.save()
    print(json.dumps({'checked':True,'problems':[key for key,_ in problems],
                      'delivery_window_open':daytime(now),'uses_d1_for_delivery':False}))


if __name__ == '__main__':
    main()
