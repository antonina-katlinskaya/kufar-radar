from datetime import datetime, timedelta, timezone
from notifications.radar_technical import bir_bot_problem, observe_bir

NOW = datetime(2026,11,18,9,0,tzinfo=timezone.utc)

def healthy(now=NOW):
    return {'ok':True,'reason':None,'now':now.isoformat(),
            'lastSuccessAt':now.isoformat(),'pendingNotifications':0,'telegramErrors':0,
            'lastScheduledDailySnapshotDate':'2026-11-18'}

def test_fresh_success_is_quiet():
    assert bir_bot_problem(healthy(),NOW) is None

def test_source_stopped_is_human_readable():
    h=healthy();h.update(ok=False,reason='stale')
    assert bir_bot_problem(h,NOW)[0]=='bir_bot_stale'

def test_night_source_pause_is_not_a_failure():
    now=NOW.replace(hour=20)
    h=healthy(now);h.update(ok=False,reason='stale')
    assert bir_bot_problem(h,now) is None

def test_delivery_is_distinct_from_collection():
    h=healthy();h.update(ok=False,reason='telegram_error',telegramErrors=1)
    assert bir_bot_problem(h,NOW)[0]=='bir_bot_delivery'

def test_queue_without_error_is_monitored():
    h=healthy();h.update(ok=False,reason='telegram_backlog',pendingNotifications=2)
    assert bir_bot_problem(h,NOW)[0]=='bir_bot_backlog'

def test_missing_morning_digest_has_grace():
    early=NOW.replace(hour=5,minute=10)
    h=healthy(early);h['lastScheduledDailySnapshotDate']='2026-11-17'
    assert bir_bot_problem(h,early) is None
    later=early+timedelta(minutes=20);h['now']=later.isoformat()
    assert bir_bot_problem(h,later)[0]=='bir_bot_digest'

def test_missing_service_requires_two_separate_checks():
    state={};p=bir_bot_problem(None,NOW)
    assert observe_bir(state,p,NOW)[0] is None
    assert observe_bir(state,p,NOW+timedelta(seconds=10))[0] is None
    assert observe_bir(state,p,NOW+timedelta(minutes=15))[0]==p

def test_transient_error_recovers_without_alert():
    state={};p=bir_bot_problem(None,NOW)
    assert observe_bir(state,p,NOW)[0] is None
    assert observe_bir(state,None,NOW+timedelta(minutes=15))[0] is None
    assert 'bir_observation' not in state

def test_old_cached_response_does_not_claim_success():
    h=healthy(NOW-timedelta(hours=1))
    assert bir_bot_problem(h,NOW)[0]=='bir_bot_invalid_health'

def test_broken_response_is_not_success():
    assert bir_bot_problem({'ok':True},NOW)[0]=='bir_bot_invalid_health'
