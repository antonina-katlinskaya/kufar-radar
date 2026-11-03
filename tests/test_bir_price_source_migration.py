import asyncio

import pytest

from radar import main


class FakeStateDB:
    def __init__(self):
        self.state = {'last_bir_success': '2026-11-03T08:52:40Z'}

    def get_state(self, key, default=None):
        return self.state.get(key, default)

    def set_state(self, key, value):
        self.state[key] = value


def test_source_upgrade_rebuilds_bir_even_if_upstream_timestamp_is_unchanged(monkeypatch):
    db = FakeStateDB()
    saved = []
    monkeypatch.setattr(main, 'history_db', lambda: object())
    monkeypatch.setattr(
        main, 'load_bir_snapshot',
        lambda _db: (['updated-promo-price'], '2026-11-03T08:52:40Z')
    )
    monkeypatch.setattr(main, 'save_bir', lambda _db, items: saved.append(items))
    assert asyncio.run(main.collect_bir(db)) is True
    assert saved == [['updated-promo-price']]
    assert db.get_state(main.BIR_CURRENT_SPECIAL_PRICE_STATE) == '1'
    assert asyncio.run(main.collect_bir(db)) is False
    assert len(saved) == 1


def test_source_upgrade_is_not_marked_done_if_snapshot_save_fails(monkeypatch):
    db = FakeStateDB()
    monkeypatch.setattr(main, 'history_db', lambda: object())
    monkeypatch.setattr(
        main, 'load_bir_snapshot',
        lambda _db: (['updated-promo-price'], '2026-11-03T08:52:40Z')
    )

    def fail_to_save(_db, _items):
        raise RuntimeError('D1 temporarily unavailable')

    monkeypatch.setattr(main, 'save_bir', fail_to_save)
    with pytest.raises(RuntimeError, match='D1 temporarily unavailable'):
        asyncio.run(main.collect_bir(db))
    assert db.get_state(main.BIR_CURRENT_SPECIAL_PRICE_STATE) is None
