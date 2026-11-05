import asyncio

import pytest

from radar import main
from radar.models import KufarListing
from radar.store import InvalidKufarSnapshot, save_kufar


class SnapshotDB:
    def __init__(self):
        self.rows = {
            '11093294': [
                {'ad_id': str(i), 'profile_id': '11093294', 'active': 1}
                for i in range(444)
            ],
            'healthy': [],
        }
        self.writes = []
        self.state = {'last_kufar_success': 'previous-success'}

    def query(self, sql, params):
        rows = self.rows[params[0]]
        if sql.startswith('SELECT COUNT(*)'):
            return [{'n': sum(row['active'] for row in rows)}]
        assert sql == 'SELECT * FROM kufar_ads WHERE profile_id=?'
        return rows

    def batch(self, statements):
        self.writes.extend(statements)

    def set_state(self, key, value):
        self.state[key] = value


def bridge_snapshot(monkeypatch, snapshots):
    monkeypatch.setattr(main, 'history_db', lambda: object())
    monkeypatch.setattr(
        main, 'load_kufar_profile_snapshot',
        lambda _source, profile_id: (
            snapshots[profile_id], {'last_success_at': 'new-success'}
        ),
    )


@pytest.mark.parametrize('count', [224, 231])
def test_size_guard_rejects_before_any_write(count):
    db = SnapshotDB()
    with pytest.raises(InvalidKufarSnapshot, match=f'got {count}, previous active 444'):
        save_kufar(db, [None] * count, '11093294')
    assert db.writes == []
    assert db.state == {'last_kufar_success': 'previous-success'}


@pytest.mark.parametrize('count', [224, 231])
def test_rejected_profile_is_excluded_without_marking_snapshot_fresh(monkeypatch, capsys, count):
    db = SnapshotDB()
    bridge_snapshot(monkeypatch, {'11093294': [None] * count})
    items, changed, previous = asyncio.run(main.collect_kufar(db, {'id': '11093294'}))

    assert (items, changed, previous) == ([], [], 444)
    assert db.writes == []
    assert db.state == {'last_kufar_success': 'previous-success'}
    assert len(db.rows['11093294']) == 444
    assert all(row['active'] == 1 for row in db.rows['11093294'])
    assert '::warning::KUFAR_SNAPSHOT_REJECTED profile=11093294' in capsys.readouterr().out

    selected, mode = main.choose_audit_targets(items, changed, previous)
    assert (selected, mode) == ([], 'empty_snapshot')
    assert main.include_active_event_targets(items, selected, {'0', '1'}) == []


def test_rejected_profile_does_not_stop_next_profile(monkeypatch):
    db = SnapshotDB()
    healthy = KufarListing(ad_id='healthy-ad', url='x', profile_id='healthy')
    bridge_snapshot(monkeypatch, {'11093294': [None] * 224, 'healthy': [healthy]})

    async def collect_profiles():
        results = []
        for profile_id in ('11093294', 'healthy'):
            results.append(await main.collect_kufar(db, {'id': profile_id}))
        return results

    rejected, accepted = asyncio.run(collect_profiles())
    assert rejected == ([], [], 444)
    assert accepted == ([healthy], [], 0)
    assert len(db.writes) == 1
    assert 'INSERT INTO kufar_ads' in db.writes[0][0]
    assert db.writes[0][1][0:2] == ['healthy-ad', 'healthy']
    assert db.state['last_kufar_count:healthy'] == '1'
    assert 'last_kufar_count:11093294' not in db.state


def test_other_storage_errors_are_not_swallowed(monkeypatch):
    db = SnapshotDB()
    bridge_snapshot(monkeypatch, {'11093294': [None] * 224})

    def fail_to_save(*_args):
        raise RuntimeError('D1 API error 503')

    monkeypatch.setattr(main, 'save_kufar', fail_to_save)
    with pytest.raises(RuntimeError, match='D1 API error 503'):
        asyncio.run(main.collect_kufar(db, {'id': '11093294'}))
    assert db.writes == []
    assert db.state == {'last_kufar_success': 'previous-success'}
