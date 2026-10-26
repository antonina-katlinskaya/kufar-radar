import unittest
from realt_test.bridge_bir import success_record,eligible
from realt_test.github_store import REPO

class BridgeTests(unittest.TestCase):
    def test_only_successful_record_from_exact_bir_step(self):
        log='\n'.join(['2026-10-26T15:00:00Z {"ok":true,"scanId":"wrong-stage","sourceCount":1}',
                       '2026-10-26T15:01:10Z {"ok":true,"scanId":"bir-scan","sourceCount":1}',
                       '2026-10-26T15:02:10Z {"ok":true,"scanId":"kufar-scan"}'])
        self.assertEqual(success_record(log,'2026-10-26T15:01:00Z','2026-10-26T15:01:59Z')['scanId'],'bir-scan')
    def test_incomplete_or_rejected_scan_never_exports(self):
        with self.assertRaises(RuntimeError):success_record('2026-10-26T15:01:10Z {"ok":false,"scanId":"x"}', '2026-10-26T15:01:00Z','2026-10-26T15:01:59Z')
    def test_forks_or_other_branches_are_rejected(self):
        run={'name':'Radar','head_branch':'main','head_repository':{'full_name':REPO},'status':'completed'}
        self.assertTrue(eligible(run))
        self.assertFalse(eligible({**run,'head_branch':'untrusted'}))
        self.assertFalse(eligible({**run,'head_repository':{'full_name':'other/fork'}}))

    def test_fractional_log_time_after_second_precision_step_end(self):
        log='2026-10-26T15:37:44.4211015Z {"ok":true,"skipped":true,"reason":"fresh_snapshot","checked_at":"2026-10-26T15:30:23.329Z"}'
        self.assertEqual(success_record(log,'2026-10-26T15:37:43Z','2026-10-26T15:37:44Z')['checked_at'],'2026-10-26T15:30:23.329Z')
