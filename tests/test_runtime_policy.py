from datetime import datetime
from zoneinfo import ZoneInfo
import json
from radar.main import (
    should_live_notify, fmt_area, fmt_dt_minsk, choose_audit_targets,
    include_active_event_targets, enqueue_pending_audits,
    summary_line, summary_overview, summary_link_keyboard, telegram_html,
    bot_action, CHECK_BUTTON, MAIN_KEYBOARD, start_payload,
    subscribed_chat_ids, add_subscriber, consume_invite, process_updates,
    SUBSCRIBERS_STATE, INVITE_TOKEN_STATE, profile_label,
    split_mass_records, fresh_listing_ids,
)
from radar.models import KufarListing

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

def test_new_profile_baseline_audits_only_listings_touched_today():
    today=KufarListing(
      ad_id='1',url='x',profile_id='11077002',
      raw={'list_time':'2026-09-23T05:04:51Z'}
    )
    old=KufarListing(
      ad_id='2',url='y',profile_id='11077002',
      raw={'list_time':'2026-09-22T20:59:59Z'}
    )
    targets,mode=choose_audit_targets(
      [today,old],[today,old],0,audit_today_on_baseline=True,
      local_now=datetime(2026,9,23,9,0,tzinfo=MINSK)
    )
    assert targets==[today]
    assert mode=='baseline_today_only'

def test_bulk_change_is_not_discarded():
    items=list(range(1848)); changed=list(range(1846))
    targets,mode=choose_audit_targets(items,changed,1848)
    assert targets==changed
    assert mode=='bulk_incremental'

def test_small_incremental_change_is_audited():
    items=list(range(1848)); changed=['new','edited']
    targets,mode=choose_audit_targets(items,changed,1848)
    assert targets==changed
    assert mode=='incremental'

def test_bir_refresh_rechecks_only_ads_with_current_active_events():
    first=KufarListing(ad_id='1',url='x',profile_id='11077002')
    second=KufarListing(ad_id='2',url='y',profile_id='11077002')
    unrelated=KufarListing(ad_id='3',url='z',profile_id='11077002')
    targets=include_active_event_targets(
      [first,second,unrelated],[first],{'1','2'}
    )
    assert targets==[first,second]

def test_persistent_keyboard_buttons_are_actions():
    assert bot_action(CHECK_BUTTON)=='check'
    assert MAIN_KEYBOARD==[[CHECK_BUTTON]]
    assert bot_action('/check')=='check'
    assert bot_action('/violations')=='state'
    assert bot_action('/invite')=='invite'
    assert bot_action('неизвестно') is None

class FakeDB:
    def __init__(self,state=None):
        self.state=dict(state or {})
    def get_state(self,key,default=None):
        return self.state.get(key,default)
    def set_state(self,key,value):
        self.state[key]=value

def test_pending_queue_keeps_changed_ad_until_audit_finishes():
    item=KufarListing(ad_id='42',url='x',profile_id='11077002')
    pending=enqueue_pending_audits({},[item])
    assert pending['42']['profile_id']=='11077002'
    assert pending['42']['reason']=='new_or_changed'
    assert pending['42']['attempts']==0

def test_strict_recheck_uses_kufar_publication_time_not_legacy_versions():
    today=KufarListing(ad_id='1',url='x',profile_id='p',raw={'list_time':'2026-09-24T08:00:00Z'})
    old=KufarListing(ad_id='2',url='x',profile_id='p',raw={'list_time':'2026-09-22T08:00:00Z'})
    assert fresh_listing_ids([today,old],datetime(2026,9,24,16,0,tzinfo=MINSK))=={'1'}

def test_five_same_kind_events_are_grouped_into_one_mass_notice():
    records=[]
    for n in range(5):
        listing=KufarListing(ad_id=str(n),url='x',profile_id='11077002')
        records.append(({'field_name':'address','new_value':'Квартал','bir_value':'Улица, 2'},listing))
    mass,singles=split_mass_records(records)
    assert singles==[]
    assert len(mass)==1 and mass[0][0]=='address' and len(mass[0][2])==5

class FakeTelegram:
    def __init__(self,updates=None):
        self.updates=list(updates or [])
        self.sent=[]
    def get_updates(self,offset=None):
        return self.updates
    def send(self,chat_id,text,**kwargs):
        self.sent.append((str(chat_id),text,kwargs))
    def answer_callback(self,*args,**kwargs):
        pass

def test_invite_adds_second_subscriber_once():
    db=FakeDB({'telegram_chat_id':'100',INVITE_TOKEN_STATE:'secret-link'})
    assert subscribed_chat_ids(db)==['100']
    assert consume_invite(db,'200','secret-link')
    assert subscribed_chat_ids(db)==['100','200']
    assert json.loads(db.state[SUBSCRIBERS_STATE])==['100','200']
    assert db.state[INVITE_TOKEN_STATE]==''
    assert not consume_invite(db,'300','secret-link')

def test_sister_start_gets_keyboard_and_current_summary_request():
    db=FakeDB({'telegram_chat_id':'100',INVITE_TOKEN_STATE:'secret-link'})
    tg=FakeTelegram([{
      'update_id':7,
      'message':{'chat':{'id':200,'type':'private'},'text':'/start secret-link'},
    }])
    force,show,joined=process_updates(db,tg)
    assert force==set() and show==set() and joined=={'200'}
    assert subscribed_chat_ids(db)==['100','200']
    assert tg.sent[0][2]['reply_keyboard']==MAIN_KEYBOARD

def test_manual_check_responds_to_requesting_subscriber():
    db=FakeDB({
      'telegram_chat_id':'100',
      SUBSCRIBERS_STATE:json.dumps(['100','200']),
    })
    tg=FakeTelegram([{
      'update_id':8,
      'message':{'chat':{'id':200,'type':'private'},'text':CHECK_BUTTON},
    }])
    force,show,joined=process_updates(db,tg)
    assert force=={'200'} and show==set() and joined==set()

def test_start_payload_accepts_telegram_deep_link_format():
    assert start_payload('/start abc_DEF-123')=='abc_DEF-123'
    assert start_payload('/start@kufar_radarr_bot abc123')=='abc123'
    assert start_payload('/start') is None

def test_event_time_is_shown_in_minsk_time():
    assert fmt_dt_minsk('2026-09-21T05:16:00Z')=='21.09.2026, 08:16'
    assert fmt_dt_minsk(1790034960000)=='22.09.2026, 02:56'

def test_summary_shows_kufar_and_detection_times():
    row={
      'field_name':'price','new_value':'45000',
      'profile_id':'11077002',
      'bir_value':json.dumps({'regular':47000,'fast':46000}),
      'building_name':'11.2','address':'Игоря Лученка ул, 22, Минск',
      'unit_no':'4.47','rooms':1,'area':29.6,'floor':4,
      'url':'https://re.kufar.by/vi/1','object_key':'x',
      'kufar_raw_json':json.dumps({'list_time':'2026-09-21T05:16:00Z'}),
      'bir_raw_json':json.dumps({'house_href':'/dom-mediteranian/'}),
      'occurred_at':'2026-09-21T05:21:00Z',
    }
    out=summary_line(row,'2026-09-21T05:20:00Z')
    assert '🔴 **НЕ СОВПАДАЕТ ЦЕНА**' in out
    assert '👤 **Ирина Барашенко**' in out
    assert '🏢 **Медитераниан · дом 11.2**' in out
    assert '🚪 Помещение № 4.47 · 1-комн. · 29,60 м² · 4 этаж' in out
    assert '**Kufar: 45 000 €**' in out
    assert '**BIR: 47 000 €**' in out
    assert '**Спеццена BIR: 46 000 €**' in out
    assert '🕒 Kufar 21.09 08:16 · радар 21.09 08:21 · BIR 21.09 08:20' in out
    assert summary_link_keyboard(row)==[[
      {'text':'Открыть Kufar','url':'https://re.kufar.by/vi/1'},
      {'text':'Открыть BIR','url':'https://bir.by/dom-mediteranian/'},
    ]]
    rendered=telegram_html(out)
    assert '<b>Kufar: 45 000 €</b>' in rendered
    assert '<b>BIR: 47 000 €</b>' in rendered
    assert '**' not in rendered

def test_morning_overview_is_short_and_scannable():
    rows=[
      {'field_name':'area','profile_id':'11093294'},
      {'field_name':'floor','profile_id':'11077002'},
    ]
    out=summary_overview(
      rows,'2026-09-22T05:02:00Z',mode='morning',
      local_now=datetime(2026,9,22,8,2,tzinfo=MINSK)
    )
    assert '☀️ **УТРЕННЯЯ ПРОВЕРКА — 22.09**' in out
    assert '⚠️ **Найдено расхождений: 2**' in out
    assert '📐 Площадь — 1' in out
    assert '🏢 Этаж — 1' in out
    assert '👤 Алёна Довгун — 1' in out
    assert '👤 Ирина Барашенко — 1' in out
    assert 'Проверка завершена в 08:02' in out
    assert 'Управление радаром' not in out

def test_profile_labels_use_confirmed_kufar_ids():
    assert profile_label('11093294')=='Алёна Довгун'
    assert profile_label('11077002')=='Ирина Барашенко'
    assert profile_label('11080367')=='Хатковская'
