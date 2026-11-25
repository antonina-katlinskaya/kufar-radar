from datetime import datetime
from unittest.mock import Mock
import unittest

from radar.audit import AuditSession
from radar.house_directory import HOUSE_DIRECTORY
from radar.main import actionable_event_records, comparison_lines, flush_auto_queue, is_commercial_listing
from radar.models import KufarListing, BirListing
from radar.years import house_year_index


class HouseYearTests(unittest.TestCase):
    def setUp(self):
        self.k = KufarListing('ad', '', 'profile', address=HOUSE_DIRECTORY['11.2'],
                              raw={'ad_parameters':[{'p':'year_built','v':2026}]})
        self.obj = BirListing('bir', 'Дом 11.2', raw={'god':2027,'deadline':'2027-10-01'})
        self.session = AuditSession.__new__(AuditSession)
        self.session.active = {}
        self.session.statements = []

    def compare(self):
        self.session.house_years = house_year_index([self.obj])
        return self.session.sync(self.k, {'status':'OK','mismatches':{}})

    def test_year_delivery_and_resolution(self):
        events = self.compare()
        row, _ = actionable_event_records([(events[0], self.k)])[0]
        self.assertEqual(row['field_name'], 'year')
        self.assertIn('2027', ' '.join(comparison_lines(row)))
        self.k.raw['ad_parameters'][0]['v'] = 2027
        self.assertEqual(self.compare(), [])
        self.assertNotIn('year', self.session.active.get('ad', {}))

    def test_uncertain_year_or_house(self):
        for house,raw in [('11.2',{'god':2027,'deadline':'2026-01-01'}),
                          ('11.2',{}),('24.2.1',{'god':2027})]:
            self.obj.building_name='Дом '+house
            self.obj.raw=raw
            self.k.address=HOUSE_DIRECTORY[house]
            self.assertEqual(self.compare(), [])

    def test_commercial(self):
        for raw in [{'category':'1050'}, {'ad_parameters':[{'p':'category','v':1050}]}]:
            self.k.raw = raw
            self.assertTrue(is_commercial_listing(self.k))

    def test_one_failed_chat_allows_other_delivery(self):
        db, tg = Mock(), Mock()
        db.get_state.return_value='owner'
        db.query.return_value=[]
        tg.send.side_effect=[RuntimeError('unavailable'),{'result':{'message_id':12}}]
        queue=[{'id':'a','text':'fixture','pending_chats':['first','second']}]
        self.assertEqual(flush_auto_queue(db,tg,queue,datetime(2026,11,25,12)), 1)
        self.assertEqual(queue[0]['pending_chats'], ['first'])
        self.assertTrue(any('INSERT INTO telegram_delivery_receipts' in str(c) for c in db.execute.call_args_list))
