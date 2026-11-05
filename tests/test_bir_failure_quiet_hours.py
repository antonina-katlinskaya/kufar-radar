import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from notifications import bir_refresh_failure as notifications


MINSK = ZoneInfo("Europe/Minsk")


class TestBirFailureQuietHours(unittest.TestCase):
    def test_exact_boundaries(self):
        for hour, minute, allowed in [
            (0, 0, False),
            (7, 59, False),
            (8, 0, True),
            (21, 59, True),
            (22, 0, False),
            (23, 59, False),
        ]:
            with self.subTest(hour=hour, minute=minute):
                now = datetime(2026, 11, 6, hour, minute, tzinfo=MINSK)
                self.assertEqual(notifications.delivery_allowed(now), allowed)

    def test_night_failure_is_queued_without_telegram(self):
        with patch.object(notifications, "owner_chat_id", return_value="owner"), \
             patch.object(notifications, "delivery_allowed", return_value=False), \
             patch.object(notifications, "read_pending", return_value=[]), \
             patch.object(notifications, "save_pending") as saved, \
             patch.object(notifications, "send_message") as send, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "test/radar", "GITHUB_RUN_ID": "321"}), \
             patch.object(sys, "argv", ["bir_refresh_failure.py"]):
            notifications.main()
        sent = saved.call_args.args[0]
        self.assertEqual(len(sent), 1)
        self.assertIn("actions/runs/321", sent[0])
        send.assert_not_called()

    def test_morning_flush_sends_and_clears_queue(self):
        pending = ["Failure A", "Failure B"]
        written = []
        def persist(value):
            written.append(list(value))
        with patch.object(notifications, "owner_chat_id", return_value="owner"), \
             patch.object(notifications, "delivery_allowed", return_value=True), \
             patch.object(notifications, "read_pending", return_value=pending), \
             patch.object(notifications, "save_pending", side_effect=persist), \
             patch.object(notifications, "send_message") as send, \
             patch.object(sys, "argv", ["bir_refresh_failure.py", "--flush"]):
            notifications.main()
        self.assertEqual(send.call_count, 2)
        self.assertEqual(written, [["Failure B"], []])


if __name__ == "__main__":
    unittest.main()
