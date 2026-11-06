"""Do not mistake a successful periodic audit for a fresh Realt collection."""
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from realt_test.health import is_daytime_alert, is_expected_source_pause
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


    def test_overnight_defer_exits_before_telegram_or_state_writes(self):
        from realt_test.health import main as health_main, REPOSITORY
        night = datetime(2026, 11, 6, 0, 8, tzinfo=timezone.utc)
        env = {
            "GITHUB_REPOSITORY": REPOSITORY,
            "GITHUB_WORKFLOW": "Realt scheduled owner-only",
            "REALT_JOB_STATUS": "failure",
            "REALT_BIR_DEFERRED": "true",
        }
        with patch.dict(os.environ, env), \
             patch("realt_test.health.datetime") as clock, \
             patch("realt_test.health.GitHubState") as state, \
             patch("realt_test.health.Bot") as bot:
            clock.now.return_value = night
            health_main()
            state.assert_not_called()
            bot.assert_not_called()

    def test_planned_night_pause_does_not_page_owner_but_real_failures_do(self):
        overnight = datetime(2026, 11, 6, 0, 8, tzinfo=timezone.utc)  # 03:08 Minsk
        morning = datetime(2026, 11, 6, 6, 5, tzinfo=timezone.utc)  # 09:05 Minsk
        self.assertTrue(is_expected_source_pause(False, True, overnight))
        self.assertFalse(is_expected_source_pause(False, True, morning))
        self.assertFalse(is_expected_source_pause(False, False, overnight))
        self.assertFalse(is_expected_source_pause(True, True, overnight))


if __name__ == "__main__":
    unittest.main()
