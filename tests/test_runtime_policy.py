from datetime import datetime
from zoneinfo import ZoneInfo
from radar.main import should_live_notify, fmt_area, fmt_dt_minsk, choose_audit_targets

MINSK=ZoneInfo('Europe/Minsk')

def t(hour,minute=0):
    return datetime(2026,9,21,hour,minute,tzinfo=MINSK)

def test_notification_window_minsk():
    assert not should_live_notify(t(7,59))
    assert should_live_notify(t(8,0))
    assert should_live_notify(t(20,59))
    assert not should_live_notify(t(21,0))

def test_area_keeps_hundredths():
    assert fmt_area(30.4)=='30,40'
    assert fmt_area(30.41)=='30,41'

def test_first_snapshot_is_silent_baseline():
    items=list(range(1848)); changed=list(items)
    targets,mode=choose_audit_targets(items,changed,0)
    assert targets==[]
    assert mode=='baseline_only'

def test_suspicious_bulk_change_is_silent_rebaseline():
    items=list(range(1848)); changed=list(range(1846))
    targets,mode=choose_audit_targets(items,changed,1848)
    assert targets==[]
    assert mode=='bulk_rebaseline'

def test_small_incremental_change_is_audited():
    items=list(range(1848)); changed=['new','edited']
    targets,mode=choose_audit_targets(items,changed,1848)
    assert targets==changed
    assert mode=='incremental'

def test_event_time_is_shown_in_minsk_time():
    assert fmt_dt_minsk('2026-09-21T05:16:00Z')=='21.09.2026, 08:16'
    assert fmt_dt_minsk(1790034960000)=='22.09.2026, 02:56'
