"""One private migration/pause notice; never uses subscriber lists or D1."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from realt_test.github_store import GitHubState
from realt_test.notify import Bot, OWNER_ID, validate_owner, REPOSITORY

def is_daytime_alert(now):
    # First daytime collection is scheduled for 07:10 Minsk.
    # Allow it to finish before warning about yesterday's data.
    hour = (now.astimezone(timezone(timedelta(hours=3)))).hour
    return 9 <= hour < 22


def main():
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY or os.environ.get('GITHUB_WORKFLOW') != 'Realt scheduled owner-only':
        raise RuntimeError('Health notice is restricted to owner workflow')
    success=os.environ.get('REALT_JOB_STATUS')=='success'
    report=Path('realt_test/results.json')
    outcome=json.loads(report.read_text()) if success and report.exists() else {}
    stale=bool(outcome.get('source_stale'))
    now=datetime.now(timezone.utc)
    if stale and not is_daytime_alert(now):
        print(json.dumps({'source_stale':True,'alert_skipped':'outside Minsk daytime collection window'}))
        return
    db=GitHubState()
    baseline=success and bool(outcome.get('notification_paused')) and not stale
    day=now.date().isoformat()
    key=('realt_health_stale_'+day if stale else
         ('realt_health_baseline_ready_v1' if baseline else 'realt_health_migrated_v1')
         if success else 'realt_health_paused_'+day)
    if db.get_state(key):return
    bot=Bot(os.environ['TELEGRAM_BOT_TOKEN'])
    validate_owner(db.get_state('realt_owner_id'),bot.call('getChat',{'chat_id':OWNER_ID}))
    link=f"https://github.com/{REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    text=('✅ Realt Radar: перенос состояния в GitHub проверен. Свежий снимок Bir прочитан из GitHub. История отправок сохранена. Kufar не изменён.' if success else
          '⏸ Realt Radar: проверка не завершена. Возможна задержка свежего снимка или ошибка запуска. Ценовые предупреждения по устаревшим данным не отправляются. Kufar не изменён.')
    if baseline:text='✅ Realt Radar: архивная история и отметки прежних отправок восстановлены в GitHub. Свежий Bir прочитан из GitHub. Для новых ценовых уведомлений ожидается свежий снимок сборщика Realt. Kufar не изменён.'
    if stale:
        latest=str((outcome.get('source') or {}).get('latest_snapshot_at') or 'неизвестно')
        text=('⏸ Realt Radar: источник Realt НЕ обновился по расписанию. '
              'Последний полный снимок: '+latest+'.\n'
              'Сверка и ценовые уведомления приостановлены до нового полного снимка. '
              'Успешный запуск проверки Bir не означает, что Realt свежий.')
    # Persist a claim before the external side effect; uncertain delivery is never retried blindly.
    db.set_state(key,json.dumps({'status':'claimed','run':link}))
    sent=bot.call('sendMessage',{'chat_id':OWNER_ID,'text':text+'\n'+link})
    db.set_state(key,json.dumps({'status':'delivered','message_id':sent['message_id'],'run':link}))
    Path('realt_test/health_receipt.json').write_text(json.dumps({'owner_verified':True,'message_id':sent['message_id'],'migration_success':success,'waiting_for_fresh_realt':bool(baseline),'run':link}))
    print(json.dumps({'owner_verified':True,'message_id':sent['message_id'],'migration_success':success,'waiting_for_fresh_realt':bool(baseline)}))

if __name__=='__main__':main()
