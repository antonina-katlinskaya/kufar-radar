import unittest
from realt_test.bridge_bir import success_record, eligible, trusted_candidates, STEPS, report_ready
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

    def test_accepts_independent_bir_history_without_untrusted_branches(self):
        self.assertEqual(STEPS['Bir history scan'], 'Scan Bir.by and update existing D1')
        history = {
            'id': 12, 'name': 'Bir history scan', 'head_branch': 'main',
            'head_repository': {'full_name': REPO}, 'status': 'completed',
            'conclusion': 'success', 'created_at': '2026-11-05T20:34:15Z',
        }
        radar = {
            'id': 13, 'name': 'Radar', 'head_branch': 'main',
            'head_repository': {'full_name': REPO}, 'status': 'completed',
            'conclusion': 'success', 'created_at': '2026-11-05T20:07:37Z',
        }
        self.assertTrue(eligible(history))
        self.assertEqual([x['id'] for x in trusted_candidates(radar, [history, radar])],
                         [12, 13])
        self.assertEqual(len(trusted_candidates(history, [history])), 1)
        with self.assertRaises(RuntimeError):
            trusted_candidates({**history, 'head_repository': {'full_name': 'attacker/fork'}}, [])

    def test_failed_source_does_not_count_as_verified_refresh(self):
        history = {
            'id': 12, 'name': 'Bir history scan', 'head_branch': 'main',
            'head_repository': {'full_name': REPO}, 'status': 'completed',
            'conclusion': 'failure', 'created_at': '2026-11-05T20:34:15Z',
        }
        self.assertEqual(trusted_candidates(history, []), [])

    def test_ready_output_explicitly_gates_notification_steps(self):
        import os
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            output = os.path.join(folder, 'output')
            with patch.dict(os.environ, {'GITHUB_OUTPUT': output}):
                report_ready(False, 'No verified source')
                report_ready(True, 'Verified source')
            with open(output, encoding='utf-8') as f:
                self.assertEqual(f.read().splitlines(), ['ready=false', 'ready=true'])

    def test_fractional_log_time_after_second_precision_step_end(self):
        log='2026-10-26T15:37:44.4211015Z {"ok":true,"skipped":true,"reason":"fresh_snapshot","checked_at":"2026-10-26T15:30:23.329Z"}'
        self.assertEqual(success_record(log,'2026-10-26T15:37:43Z','2026-10-26T15:37:44Z')['checked_at'],'2026-10-26T15:30:23.329Z')
