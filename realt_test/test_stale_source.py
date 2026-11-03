"""Do not mistake a successful periodic audit for a fresh Realt collection."""
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from realt_test.health import is_daytime_alert
from realt_test.run import stale_source_report


class RealtStalenessTests(unittest.TestCase):
    def test_expired_source_disables_notifications_and_returns_no_old_reviews(self):
        record = stale_source_report({
            "unchanged": True, "source_stale": True,
            "latest_snapshot_at": "2026-10-28T16:50:00Z",
        })
        self.assertEqual(record["items"], [])
        self.assertTrue(record["notification_paused"])
        self.assertTrue(record["source_stale"])
        self.assertIn("2026-10-28", record["coverage_warning"])

    def test_run_ignores_previously_pending_reviews_if_source_expired(self):
        from realt_test.run import run
        previous = {"pending_result": {"items": [{"status": "REVIEW"}]}}
        fresh = {"unchanged": True, "source_stale": True,
                 "latest_snapshot_at": "2026-10-28T16:50:00Z"}
        with patch.dict(os.environ, {"REALT_CONTINUOUS": "1"}), \
             patch("realt_test.github_store.GitHubState", return_value=object()), \
             patch("realt_test.incremental.load", return_value=previous), \
             patch("realt_test.incremental.source", return_value=({}, fresh)), \
             patch("realt_test.run.write_reports") as writer:
            run()
            report = writer.call_args.args[0]
            self.assertEqual(report["items"], [])
            self.assertTrue(report["notification_paused"])

    def test_only_send_missing_collection_warning_during_minsk_business_hours(self):
        self.assertFalse(is_daytime_alert(datetime(2026, 11, 3, 5, tzinfo=timezone.utc)))
        self.assertTrue(is_daytime_alert(datetime(2026, 11, 3, 6, tzinfo=timezone.utc)))
        self.assertFalse(is_daytime_alert(datetime(2026, 11, 3, 20, tzinfo=timezone.utc)))


if __name__ == "__main__":
    unittest.main()
