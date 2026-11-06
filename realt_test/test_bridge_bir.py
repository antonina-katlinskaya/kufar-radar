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
                report_ready(False, 'No verified source', deferred=True)
                report_ready(True, 'Verified source')
            with open(output, encoding='utf-8') as f:
                self.assertEqual(f.read().splitlines(), ['ready=false', 'deferred=true', 'ready=true', 'deferred=false'])

    def test_main_defers_missing_bir_source_without_export(self):
        import json
        import os
        import tempfile
        from datetime import datetime, timezone, timedelta
        from pathlib import Path
        from unittest.mock import patch
        from realt_test.bridge_bir import main
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp, 'event.json')
            event.write_text('{}', encoding='utf-8')
            output = Path(tmp, 'output')
            old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            env = {'GITHUB_EVENT_PATH': str(event), 'GITHUB_OUTPUT': str(output),
                   'GITHUB_TOKEN': 'not-a-real-token',
                   'BIR_EXPORT_META_PATH': str(Path(tmp, 'bir-meta.json'))}
            with patch.dict(os.environ, env), \
                 patch('realt_test.bridge_bir.GitHubFile') as saved, \
                 patch('realt_test.bridge_bir.httpx.Client'), \
                 patch('realt_test.bridge_bir.get', return_value={'workflow_runs': []}), \
                 patch('realt_test.bridge_bir.export_snapshot') as exporter:
                saved.return_value.read.return_value = {'complete': True, 'checked_at': old}
                main()
                exporter.assert_not_called()
            self.assertEqual(output.read_text(encoding='utf-8'), 'ready=false\ndeferred=true\n')

    def test_main_accepts_verified_independent_bir_history_record(self):
        import json
        import os
        import tempfile
        from datetime import datetime, timezone, timedelta
        from pathlib import Path
        from unittest.mock import patch
        from realt_test.bridge_bir import main
        now = datetime.now(timezone.utc).replace(microsecond=0)
        iso = lambda value: value.isoformat().replace('+00:00', 'Z')
        history = {'id': 105, 'name': 'Bir history scan',
                   'head_branch': 'main', 'head_repository': {'full_name': REPO},
                   'status': 'completed', 'conclusion': 'success',
                   'created_at': iso(now-timedelta(minutes=2))}
        step = {'name': STEPS['Bir history scan'], 'conclusion': 'success',
                'started_at': iso(now-timedelta(minutes=1)),
                'completed_at': iso(now+timedelta(minutes=1))}
        record = json.dumps({'ok': True, 'reason': 'fresh_snapshot',
                             'checked_at': iso(now-timedelta(minutes=1))})
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp, 'event.json')
            event.write_text(json.dumps({'workflow_run': history}), encoding='utf-8')
            output = Path(tmp, 'output')
            meta = Path(tmp, 'bir-meta.json')
            env = {'GITHUB_EVENT_PATH': str(event), 'GITHUB_OUTPUT': str(output),
                   'GITHUB_TOKEN': 'not-a-real-token', 'BIR_EXPORT_META_PATH': str(meta)}
            with patch.dict(os.environ, env), \
                 patch('realt_test.bridge_bir.GitHubFile') as saved, \
                 patch('realt_test.bridge_bir.httpx.Client') as client, \
                 patch('realt_test.bridge_bir.get',
                       side_effect=[{'workflow_runs': [history]},
                                    {'jobs': [{'id': 18, 'steps': [step]}]}]), \
                 patch('realt_test.bridge_bir.export_snapshot') as exporter:
                saved.return_value.read.return_value = {
                    'complete': True, 'checked_at': iso(now-timedelta(hours=2))}
                response = client.return_value.__enter__.return_value.get.return_value
                response.is_success = True
                response.text = iso(now) + ' ' + record
                main()
                exporter.assert_called_once()
            self.assertEqual(output.read_text(encoding='utf-8'), 'ready=true\ndeferred=false\n')
            self.assertEqual(json.loads(meta.read_text(encoding='utf-8'))['ok'], True)

    def test_fractional_log_time_after_second_precision_step_end(self):
        log='2026-10-26T15:37:44.4211015Z {"ok":true,"skipped":true,"reason":"fresh_snapshot","checked_at":"2026-10-26T15:30:23.329Z"}'
        self.assertEqual(success_record(log,'2026-10-26T15:37:43Z','2026-10-26T15:37:44Z')['checked_at'],'2026-10-26T15:30:23.329Z')
