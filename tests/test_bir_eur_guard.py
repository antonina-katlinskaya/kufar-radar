"""The D1 quota guard must not suppress a real EUR price update."""
import json
import sqlite3
import unittest
from pathlib import Path


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE bir_objects(id TEXT PRIMARY KEY,present INTEGER,missing_checks INTEGER,detail_json TEXT,detail_fetched_at TEXT,house TEXT,listing_json TEXT)')
        self.db.executescript((Path(__file__).parents[1]/'migrations/d1_bir_eur_price_guard_20261103.sql').read_text())
        self.listing={'house':'24.2.2','number':'528','area':'49.62','floor':'4','rooms':'1','prices_eur':[1550,76911,1341,66540],'raw_html':'old BYN'}
        self.db.execute('INSERT INTO bir_objects VALUES(?,1,0,?,?,?,?)',('id','{}','2026-11-03','24.2.2',json.dumps(self.listing)))

    def update(self,listing):
        self.db.execute('UPDATE bir_objects SET listing_json=? WHERE id=?',(json.dumps(listing),'id'))
        return json.loads(self.db.execute('SELECT listing_json FROM bir_objects').fetchone()[0])

    def test_euro_price_change_is_saved(self):
        changed={**self.listing,'prices_eur':[1550,76911,1300,64506],'raw_html':'new EUR'}
        self.assertEqual(self.update(changed),changed)

    def test_byn_only_change_is_ignored(self):
        changed={**self.listing,'raw_html':'new BYN'}
        self.assertEqual(self.update(changed),self.listing)

    def test_legacy_collector_without_metadata_can_update_prices(self):
        changed={k:v for k,v in self.listing.items() if k!='prices_eur'}
        self.assertEqual(self.update(changed),changed)

    def test_first_population_of_prices_is_saved(self):
        legacy={k:v for k,v in self.listing.items() if k!='prices_eur'}
        self.db.execute('DELETE FROM bir_objects')
        self.db.execute('INSERT INTO bir_objects VALUES(?,1,0,?,?,?,?)',('id','{}','2026-11-03','24.2.2',json.dumps(legacy)))
        self.assertEqual(self.update(self.listing),self.listing)

if __name__=='__main__': unittest.main()
