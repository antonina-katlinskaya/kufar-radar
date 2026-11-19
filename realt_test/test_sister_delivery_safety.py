import unittest
from datetime import datetime,timezone,timedelta
from realt_test.notify import initialize_sister_baseline, filter_post_baseline, BASELINE_V2_KEY
from realt_test.dedup import fingerprint

class State:
    def __init__(self):self.values={};self.writes=0
    def get_state(self,key,default=None):return self.values.get(key,default)
    def set_state(self,key,value):self.values[key]=value;self.writes+=1

def stamp(minutes):
    return (datetime.now(timezone.utc)+timedelta(minutes=minutes)).isoformat()

def item(uid='abc',price='49376',last=None):
    return {'uuid':uid,'person':'Жанна Вакуленчик','status':'REVIEW',
            'rooms':'1','area':'31.35','price':price,'currency':'978',
            'reason':'No room/area BIR match','last_seen_at':last or stamp(-10)}

class SafetyTests(unittest.TestCase):
    def test_old_backlog_and_identical_message_suppressed(self):
        db=State();old=item();now=stamp(-10)
        report={'source':{'latest_snapshot_at':now},'bir_checked_at':stamp(-2),
                'checked':1,'items':[old]}
        self.assertTrue(initialize_sister_baseline(db,report))
        self.assertFalse(initialize_sister_baseline(db,report))
        self.assertEqual(db.writes,1)
        import json
        baseline=json.loads(db.get_state(BASELINE_V2_KEY))
        self.assertEqual(filter_post_baseline([old],baseline),[])
        self.assertEqual(filter_post_baseline([{**old,'last_seen_at':stamp(-1)}],baseline),[])
        self.assertEqual(len(filter_post_baseline([item(price='49377',last=stamp(-1))],baseline)),1)
        self.assertEqual(len(filter_post_baseline([item(uid='new',last=stamp(-1))],baseline)),1)

    def test_no_baseline_for_missing_or_incomplete_source(self):
        for report in (
            {'source':{},'checked':1,'items':[item()]},
            {'source':{'latest_snapshot_at':stamp(-10)},'checked':2,'items':[item()]},
        ):
            db=State()
            with self.assertRaises(RuntimeError): initialize_sister_baseline(db,report)
            self.assertEqual(db.writes,0)

    def test_stale_report_can_be_quietly_baselined_at_activation_time(self):
        db=State()
        report={'source':{'latest_snapshot_at':stamp(-120)},'checked':1,'items':[item()]}
        self.assertTrue(initialize_sister_baseline(db,report))
        import json
        baseline=json.loads(db.get_state(BASELINE_V2_KEY))
        self.assertEqual(filter_post_baseline([{**item(),'last_seen_at':stamp(-1)}],baseline),[])
        self.assertEqual(len(filter_post_baseline([item(uid='fresh',last=stamp(1))],baseline)),1)

if __name__=='__main__':unittest.main()
