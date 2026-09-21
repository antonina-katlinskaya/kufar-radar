from datetime import datetime
from zoneinfo import ZoneInfo
import json
from radar.main import (
    should_live_notify, fmt_area, fmt_dt_minsk, choose_audit_targets,
    summary_line, telegram_html, bot_action, CHECK_BUTTON, STATE_BUTTON
)

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

def test_persistent_keyboard_buttons_are_actions():
    assert bot_action(CHECK_BUTTON)=='check'
    assert bot_action(STATE_BUTTON)=='state'
    assert bot_action('/check')=='check'
    assert bot_action('/violations')=='state'
    assert bot_action('неизвестно') is None

def test_event_time_is_shown_in_minsk_time():
    assert fmt_dt_minsk('2026-09-21T05:16:00Z')=='21.09.2026, 08:16'
    assert fmt_dt_minsk(1790034960000)=='22.09.2026, 02:56'

def test_summary_shows_kufar_and_detection_times():
    row={
      'field_name':'price','new_value':'45000',
      'bir_value':json.dumps({'regular':47000,'fast':46000}),
      'building_name':'11.2','address':'Игоря Лученка ул, 22, Минск',
      'unit_no':'4.47','rooms':1,'area':29.6,'floor':4,
      'url':'https://re.kufar.by/vi/1','object_key':'x',
      'kufar_raw_json':json.dumps({'list_time':'2026-09-21T05:16:00Z'}),
      'bir_raw_json':json.dumps({'house_href':'/dom-mediteranian/'}),
      'occurred_at':'2026-09-21T05:21:00Z',
    }
    out=summary_line(row,'2026-09-21T05:20:00Z')
    assert 'Медитераниан (11.2)' in out
    assert 'пом. № 4.47, 1-комн., 29,60 м², 4 эт.' in out
    assert 'Kufar: **45 000 €** | BIR: **47 000 € (спец.: 46 000 €)**' in out
    assert 'Время — Kufar: 21.09.2026, 08:16 | радар: 21.09.2026, 08:21 | BIR: 21.09.2026, 08:20' in out
    rendered=telegram_html(out)
    assert '<b>45 000 €</b>' in rendered
    assert '<b>47 000 € (спец.: 46 000 €)</b>' in rendered
    assert '**' not in rendered
