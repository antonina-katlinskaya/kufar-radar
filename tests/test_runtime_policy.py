from datetime import datetime
from zoneinfo import ZoneInfo
from radar.main import should_live_notify, fmt_area

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
