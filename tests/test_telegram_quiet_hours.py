from datetime import datetime
from zoneinfo import ZoneInfo

from radar.main import (
    flush_auto_queue, queue_auto_notification, load_auto_queue,
)


class FakeDB:
    def __init__(self):
        self.state = {}
    def get_state(self, key, default=None):
        return self.state.get(key, default)
    def set_state(self, key, value):
        self.state[key] = value


class FakeTelegram:
    def __init__(self, fail_chat=None):
        self.sent = []
        self.fail_chat = fail_chat
    def send(self, chat, text, **kwargs):
        if str(chat) == str(self.fail_chat):
            raise RuntimeError('temporary Telegram failure')
        self.sent.append((str(chat), text, kwargs))


MINSK = ZoneInfo('Europe/Minsk')


def test_quiet_hours_keep_both_recipients_and_detection_time():
    db, tg = FakeDB(), FakeTelegram()
    queue = []
    text = 'Нарушение — радар 08.10 23:40'
    queue_auto_notification(db, queue, ['owner', 'sister'], text)
    assert flush_auto_queue(db, tg, queue, datetime(2026, 10, 8, 22, 0, tzinfo=MINSK)) == 0
    assert flush_auto_queue(db, tg, queue, datetime(2026, 10, 9, 7, 59, tzinfo=MINSK)) == 0
    assert tg.sent == []
    assert len(load_auto_queue(db)) == 1
    assert flush_auto_queue(db, tg, queue, datetime(2026, 10, 9, 8, 0, tzinfo=MINSK)) == 2
    assert [c for c, _, _ in tg.sent] == ['owner', 'sister']
    assert all(message == text for _, message, _ in tg.sent)
    assert load_auto_queue(db) == []


def test_failed_chat_is_retried_without_resending_to_other_chat():
    db, tg = FakeDB(), FakeTelegram(fail_chat='sister')
    queue = []
    queue_auto_notification(db, queue, ['owner', 'sister'], 'old detection')
    assert flush_auto_queue(db, tg, queue, datetime(2026, 10, 9, 8, 0, tzinfo=MINSK)) == 1
    assert [c for c, _, _ in tg.sent] == ['owner']
    assert load_auto_queue(db)[0]['pending_chats'] == ['sister']
    tg.fail_chat = None
    assert flush_auto_queue(db, tg, queue, datetime(2026, 10, 9, 8, 5, tzinfo=MINSK)) == 1
    assert [c for c, _, _ in tg.sent] == ['owner', 'sister']
    assert load_auto_queue(db) == []
