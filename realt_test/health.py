"""One private migration/pause notice; never uses subscriber lists or D1."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from realt_test.github_store import GitHubState
from realt_test.notify import Bot, OWNER_ID, validate_owner, REPOSITORY

def main():
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY or os.environ.get('GITHUB_WORKFLOW') != 'Realt scheduled owner-only':
        raise RuntimeError('Health notice is restricted to owner workflow')
    success=os.environ.get('REALT_JOB_STATUS')=='success'
    db=GitHubState()
    report=Path('realt_test/results.json')
    baseline=success and report.exists() and json.loads(report.read_text()).get('notification_paused')
    key=('realt_health_baseline_ready_v1' if baseline else 'realt_health_migrated_v1') if success else 'realt_health_paused_'+datetime.now(timezone.utc).date().isoformat()
    if db.get_state(key):return
    bot=Bot(os.environ['TELEGRAM_BOT_TOKEN'])
    validate_owner(db.get_state('realt_owner_id'),bot.call('getChat',{'chat_id':OWNER_ID}))
    link=f"https://github.com/{REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    text=('✅ Realt Radar: перенос состояния в GitHub проверен. Свежий снимок Bir прочитан из GitHub. История отправок сохранена. Kufar не изменён.' if success else
          '⏸ Realt Radar: проверка не завершена. Возможна задержка свежего снимка или ошибка запуска. Ценовые предупреждения по устаревшим данным не отправляются. Kufar не изменён.')
    if baseline:text='✅ Realt Radar: архивная история и отметки прежних отправок восстановлены в GitHub. Свежий Bir прочитан из GitHub. Для новых ценовых уведомлений ожидается свежий снимок сборщика Realt. Kufar не изменён.'
    # Persist a claim before the external side effect; uncertain delivery is never retried blindly.
    db.set_state(key,json.dumps({'status':'claimed','run':link}))
    sent=bot.call('sendMessage',{'chat_id':OWNER_ID,'text':text+'\n'+link})
    db.set_state(key,json.dumps({'status':'delivered','message_id':sent['message_id'],'run':link}))
    Path('realt_test/health_receipt.json').write_text(json.dumps({'owner_verified':True,'message_id':sent['message_id'],'migration_success':success,'waiting_for_fresh_realt':bool(baseline),'run':link}))
    print(json.dumps({'owner_verified':True,'message_id':sent['message_id'],'migration_success':success,'waiting_for_fresh_realt':bool(baseline)}))

if __name__=='__main__':main()
