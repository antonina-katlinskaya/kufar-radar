import importlib.util,json,sqlite3,unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('maintenance',Path(__file__).parents[1]/'notifications/storage_maintenance.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class RetentionTests(unittest.TestCase):
    def test_only_old_version_metadata_is_removed(self):
        db=sqlite3.connect(':memory:')
        db.execute('CREATE TABLE kufar_versions(id INTEGER PRIMARY KEY, observed_at TEXT,price_eur REAL,area REAL,raw_json TEXT)')
        payload=json.dumps({'currency':'EUR','calculator':[{'currency':'EUR','price':6654000}],'list_time':'2026-09-28','paid_services':{'vip':True},'ad_parameters':[{'p':'size','v':49.6}]})
        db.executemany('INSERT INTO kufar_versions VALUES(?,?,?,?,?)',[(1,'2000-01-01',66540,49.6,payload),(2,'2999-01-01',66540,49.6,payload)])
        db.execute(module.TASKS[0][1]);rows=db.execute('SELECT * FROM kufar_versions ORDER BY id').fetchall()
        self.assertEqual(len(rows),2);self.assertEqual(rows[0][2:4],(66540,49.6))
        raw=json.loads(rows[0][4]);self.assertNotIn('ad_parameters',raw);self.assertEqual(raw['calculator'][0]['price'],6654000);self.assertTrue(raw['paid_services']['vip'])
        self.assertEqual(rows[1][4],payload)

    def test_active_cards_and_recent_inactive_cards_are_preserved(self):
        db=sqlite3.connect(':memory:')
        db.execute('CREATE TABLE kufar_ads_live(ad_id TEXT PRIMARY KEY,present INTEGER,last_seen TEXT,raw_json TEXT)')
        payload='{"ad_parameters":[{"p":"size","v":49.6}],"currency":"EUR"}'
        db.executemany('INSERT INTO kufar_ads_live VALUES(?,?,?,?)',[('old-active',1,'2000-01-01',payload),('old-inactive',0,'2000-01-01',payload),('recent-inactive',0,'2999-01-01',payload)])
        db.execute(module.TASKS[1][1]);rows=dict(db.execute('SELECT ad_id,raw_json FROM kufar_ads_live'))
        self.assertEqual(rows['old-active'],payload);self.assertEqual(rows['recent-inactive'],payload);self.assertNotIn('ad_parameters',json.loads(rows['old-inactive']))

if __name__=='__main__':unittest.main()
