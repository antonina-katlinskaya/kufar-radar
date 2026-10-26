import base64
import json
import unittest
from datetime import datetime, timezone, timedelta
from realt_test.github_store import GitHubFile, GitHubState
from realt_test.bir_snapshot import decode

class StoreTests(unittest.TestCase):
    def seed(self):
        return {'schema':1,'migration_complete':True,'values':{'realt_owner_id':'352252956'}}
    def test_read_write_lease_and_no_cloudflare(self):
        calls=[]
        def request(method,path,body=None):
            calls.append((method,path,body))
            if method=='GET':return {'sha':'old','encoding':'base64','content':base64.b64encode(json.dumps(self.seed()).encode()).decode()}
            self.assertEqual(body['sha'],'old')
            return {'content':{'sha':'new'}}
        f=GitHubFile('realt-state','state.json',request)
        db=GitHubState(f);db.set_state('realt_key','saved')
        self.assertEqual(f.sha,'new');self.assertEqual(len(calls),2)
        db.set_state('realt_key','saved');self.assertEqual(len(calls),2)
        with self.assertRaises(RuntimeError):db.set_state('telegram_chat_id','sister')
    def test_failed_persistence_does_not_acknowledge(self):
        class Fake:
            def read(inner):return self.seed()
            def write(inner,value):raise RuntimeError('Conflict')
        db=GitHubState(Fake())
        with self.assertRaises(RuntimeError):db.set_state('realt_ack','new')
        self.assertIsNone(db.get_state('realt_ack'))
    def test_missing_migration_never_resets_dedup(self):
        class Fake:
            def read(inner):return {'schema':1,'values':{}}
        with self.assertRaises(RuntimeError):GitHubState(Fake())
    def test_fresh_complete_snapshot_and_no_rounding(self):
        now=datetime.now(timezone.utc)
        obj={'schema':1,'complete':True,'checked_at':now.isoformat(),'items':[{'object_key':'uuid','area':'44.42','rooms':1,'price_fast_eur':'59923'}]}
        rows,stamp=decode(obj,now);self.assertEqual(rows[0].area,'44.42')
        with self.assertRaises(RuntimeError):decode(obj,now+timedelta(minutes=36))
        obj['complete']=False
        with self.assertRaises(RuntimeError):decode(obj,now)
