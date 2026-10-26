import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from realt_test.notify import OWNER_ID, publish, validate_owner
from realt_test.policy import area_equal, created_in_window, decimal_value
from realt_test.run import audit, write_reports
from realt_test.sources import TRACKED, merge_snapshots

UID = next(iter(TRACKED))


def row(**values):
    return {'uuid': 'ad1', 'code': 123, 'userUuid': UID, 'person': TRACKED[UID],
            'createdAt': '2026-10-23T00:05:00+03:00', 'rooms': 1,
            'areaTotal': '46.22', 'price': '61981', 'priceCurrency': 978, **values}


def bir(**values):
    return SimpleNamespace(**{'object_key': 'b1', 'building_name': 'Дом', 'unit_no': '1',
        'rooms': 1, 'area': '46.22', 'floor': 2,
        'price_fast_eur': '61981', 'price_regular_eur': '70000', **values})


class PolicyTests(unittest.TestCase):
    def test_exact_area_no_rounding(self):
        self.assertTrue(area_equal('46,22', 46.22))
        self.assertFalse(area_equal('46.2', '46.22'))
        self.assertFalse(area_equal('46.22', '46.221'))

    def test_invalid_numbers_fail_closed(self):
        for value in (None, '', 'NaN', 'sNaN', 'Infinity', '-Infinity', 'bad'):
            self.assertIsNone(decimal_value(value))
            self.assertFalse(area_equal(value, 46.22))

    def test_window_uses_published_local_date(self):
        self.assertTrue(created_in_window('2026-10-23T00:05:00+03:00'))
        self.assertTrue(created_in_window('2026-10-26T23:59:59+03:00'))
        self.assertFalse(created_in_window('2026-10-27T00:00:00+03:00'))
        self.assertFalse(created_in_window('2026-10-22T23:59:59+03:00'))

    def test_archive_preserves_disappeared_and_deduplicates(self):
        snapshots = [('2026-10-23T12:00:00Z', [row(), row(uuid='ad2')]),
                     ('2026-10-25T12:00:00Z', [row(price=60000)])]
        merged = {r['uuid']: r for r in merge_snapshots(snapshots)}
        self.assertEqual(set(merged), {'ad1', 'ad2'})
        self.assertEqual(merged['ad1']['price'], 60000)
        self.assertEqual(merged['ad1']['first_seen_at'], snapshots[0][0])
        self.assertEqual(merged['ad2']['last_seen_at'], snapshots[0][0])

    def test_unverified_people_excluded(self):
        self.assertEqual(merge_snapshots([('2026-10-25', [row(userUuid='unknown'), row(createdAt='2026-10-27')])]), [])

    def test_conflicting_identity_aborts(self):
        with self.assertRaises(RuntimeError):
            merge_snapshots([('2026-10-25', [row(contactEmail='a.p.zenkevich@minsk.etagi.com')])])

    def test_all_four_identities_included(self):
        rows = [row(userUuid=uid, uuid=uid) for uid in TRACKED]
        self.assertEqual({r['person'] for r in merge_snapshots([('2026-10-25', rows)])}, set(TRACKED.values()))

    def test_special_price_only_and_floor_ignored(self):
        result = audit([row(storey=99), row(uuid='regular', price=70000)], [bir()], '2026-10-26', {})
        self.assertEqual([r['status'] for r in result['items']], ['OK', 'REVIEW'])
        self.assertEqual(result['items'][1]['bir_room_area_candidates'][0]['special_price_eur'], '61981')

    def test_unknown_currency_is_not_violation(self):
        result = audit([row(priceCurrency='BYN')], [bir()], '2026-10-26', {})
        self.assertEqual(result['items'][0]['status'], 'REVIEW')
        self.assertIn('не установлено', result['items'][0]['reason'])

    def test_nearby_area_is_only_hint(self):
        result = audit([row(areaTotal='46.2')], [bir()], '2026-10-26', {})
        item = result['items'][0]
        self.assertEqual(item['status'], 'REVIEW')
        self.assertEqual(item['matching_bir_keys'], [])
        self.assertEqual(len(item['nearest_area_hints_not_matches']), 1)


class OwnerTests(unittest.TestCase):
    def test_reject_sister_group_or_changed_owner(self):
        for owner, chat in [('1037292158', {'id': 1037292158, 'type': 'private'}),
                            (OWNER_ID, {'id': OWNER_ID, 'type': 'group'}),
                            ('other', {'id': OWNER_ID, 'type': 'private'})]:
            with self.assertRaises(RuntimeError):
                validate_owner(owner, chat)

    def test_publish_has_one_recipient_and_no_shared_state(self):
        class FakeBot:
            calls = []
            def call(self, method, payload, files=None):
                self.calls.append((method, payload))
                if method == 'getChat':
                    return {'id': int(OWNER_ID), 'type': 'private'}
                if method == 'sendMessage':
                    return {'message_id': 123}
                return True
        bot = FakeBot()
        result = audit([row(price='70000')], [bir()], '2026-10-26', {})
        old = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.chdir(tmp)
                write_reports(result)
                receipt = publish(result, OWNER_ID, bot, 'https://github.com/example/run')
                self.assertEqual(len(receipt['message_ids']), 1)
                self.assertEqual(len(receipt['documents_sent']), 0)
                self.assertTrue(Path('realt_test/notification_receipt.json').exists())
        finally:
            os.chdir(old)
        self.assertTrue(all(str(p['chat_id']) == OWNER_ID for _, p in bot.calls))
        self.assertEqual([m for m, _ in bot.calls], ['getChat', 'sendMessage'])
        self.assertIn('inline_keyboard', bot.calls[1][1]['reply_markup'])

    def test_delta_message_only_mentions_new_case(self):
        class FakeBot:
            def __init__(self): self.calls = []
            def call(self, method, payload, files=None):
                self.calls.append((method, payload))
                if method == 'getChat': return {'id': int(OWNER_ID), 'type': 'private'}
                if method == 'sendMessage': return {'message_id': 202}
                return True
        bot = FakeBot()
        r = audit([row(uuid='ad1', code=111), row(uuid='ad2', code=222)], [bir()], '2026-10-26', {})
        selected = [{**r['items'][0], 'status': 'REVIEW', 'reason': 'Manual review'}]
        old = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.chdir(tmp)
                write_reports({**r, 'items': selected})
                publish(r, OWNER_ID, bot, 'https://github.com/example/run', review_items=selected)
        finally:
            os.chdir(old)
        msg = next(payload['text'] for method, payload in bot.calls if method == 'sendMessage')
        self.assertIn('https://realt.by/sale-flats/object/111/', bot.calls[1][1]['reply_markup']['inline_keyboard'][0][0]['url'])
        self.assertNotIn('222', msg)

    def test_wrong_recipient_never_sends(self):
        class FakeBot:
            calls = []
            def call(self, method, payload):
                self.calls.append(method)
                return {'id': 1037292158, 'type': 'private'}
        bot = FakeBot()
        with self.assertRaises(RuntimeError):
            publish({}, OWNER_ID, bot, 'https://github.com/example/run')
        self.assertEqual(bot.calls, ['getChat'])


if __name__ == '__main__':
    unittest.main()
