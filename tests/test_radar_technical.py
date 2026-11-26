import unittest
from datetime import datetime, timezone, timedelta
from notifications.radar_technical import daytime, pipeline_problem, observe_pipeline


class TechnicalTests(unittest.TestCase):
    def test_minsk_quiet_hours(self):
        for utc_hour, expected in [(4, False), (5, True), (18, True), (19, False), (23, False)]:
            self.assertEqual(daytime(datetime(2026,11,18,utc_hour,tzinfo=timezone.utc)),expected)

    def test_quota_has_human_reason(self):
        key,text=pipeline_problem({'BIR_REFRESH_OUTCOME':'failure'}, {'codes':[7500]})
        self.assertEqual(key,'bir_database')
        self.assertIn('03:00',text)
        self.assertIn('квота',text)

    def test_skipped_scan_is_not_an_error(self):
        self.assertIsNone(pipeline_problem({'BIR_REFRESH_OUTCOME':'success','RADAR_SCAN_OUTCOME':'skipped'},{}))

    def test_parent_failure_takes_priority(self):
        self.assertEqual(pipeline_problem({'BIR_REFRESH_OUTCOME':'failure','RADAR_SCAN_OUTCOME':'failure'}, {})[0], 'bir_database')

    def test_bridge_failure(self):
        self.assertEqual(pipeline_problem({'BIR_REFRESH_OUTCOME':'success','KUFAR_BRIDGE_OUTCOME':'failure'}, {})[0], 'kufar_source')

    def test_pipeline_transient_failure_then_success(self):
        state={}
        now=datetime(2026,11,26,12,tzinfo=timezone.utc)
        problem=('radar','temporary failure')
        self.assertEqual(observe_pipeline(state,problem,now),(None,True))
        self.assertEqual(observe_pipeline(state,None,now+timedelta(minutes=15),True),(None,True))
        self.assertNotIn('pipeline_observation',state)

    def test_pipeline_persistent_failure(self):
        state={}
        now=datetime(2026,11,26,12,tzinfo=timezone.utc)
        problem=('radar','failure')
        self.assertEqual(observe_pipeline(state,problem,now),(None,True))
        self.assertEqual(observe_pipeline(state,problem,now+timedelta(seconds=60)),(None,False))
        self.assertEqual(observe_pipeline(state,problem,now+timedelta(minutes=15)),(problem,True))

    def test_pipeline_skipped_not_recovery(self):
        state={}
        now=datetime(2026,11,26,12,tzinfo=timezone.utc)
        problem=('radar','failure')
        observe_pipeline(state,problem,now)
        self.assertEqual(observe_pipeline(state,None,now+timedelta(minutes=5)),(None,False))
        self.assertIn('pipeline_observation',state)

    def test_pipeline_quota_immediate(self):
        now=datetime(2026,11,26,12,tzinfo=timezone.utc)
        problem=('bir_database','quota')
        self.assertEqual(observe_pipeline({},problem,now,quota=True),(problem,True))
