from __future__ import annotations

import gc
import importlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bewaarhet import database, rate_limiter


class RateLimiterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings = SimpleNamespace(database_path=Path(self.temp_dir.name) / 'bewaarhet.sqlite3')
        self.settings_patcher = patch('bewaarhet.database.settings', self.settings)
        self.settings_patcher.start()
        database.init_db()
        self.rl = rate_limiter

    def tearDown(self) -> None:
        self.settings_patcher.stop()
        gc.collect()
        self.temp_dir.cleanup()

    def _fill(self, sender: str, action: str, count: int, now: int = 1000) -> None:
        for _ in range(count):
            result = self.rl.check_rate_limit(sender, action, now=now)
            self.assertTrue(result.allowed)

    def test_soft_limit_triggers_delay_without_blocking(self) -> None:
        self._fill('user@example.com', 'search', 30)

        with (
            patch.object(self.rl, '_now', return_value=1000),
            patch.object(self.rl.time, 'sleep') as sleep,
            patch.object(self.rl, 'send_html') as send_html,
        ):
            allowed = self.rl.apply_rate_limit_or_reply('User@Example.com', 'search')

        self.assertTrue(allowed)
        sleep.assert_called_once_with(self.rl.SOFT_BACKOFF_SECONDS)
        send_html.assert_not_called()

    def test_hard_limit_blocks_and_sends_friendly_reply(self) -> None:
        self._fill('user@example.com', 'search', 60)

        with (
            patch.object(self.rl, '_now', return_value=1000),
            patch.object(self.rl, 'send_html') as send_html,
        ):
            allowed = self.rl.apply_rate_limit_or_reply('user@example.com', 'search')

        self.assertFalse(allowed)
        send_html.assert_called_once()
        self.assertEqual(send_html.call_args.args[0], 'user@example.com')
        self.assertIn('Probeer het later opnieuw', send_html.call_args.args[1])
        self.assertIn('Er zijn tijdelijk erg veel verzoeken ontvangen vanaf dit e-mailadres.', send_html.call_args.args[2])

    def test_cooldown_expires_correctly(self) -> None:
        self._fill('user@example.com', 'search', 60, now=1000)

        blocked = self.rl.check_rate_limit('user@example.com', 'search', now=1000)
        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.cooldown_until, 4600)

        still_blocked = self.rl.check_rate_limit('user@example.com', 'search', now=2000, increment=False)
        self.assertFalse(still_blocked.allowed)

        after_cooldown = self.rl.check_rate_limit('user@example.com', 'search', now=5000)
        self.assertTrue(after_cooldown.allowed)
        self.assertFalse(after_cooldown.hard_exceeded)

    def test_search_limits_are_separate_from_upload_limits(self) -> None:
        self._fill('user@example.com', 'search', 30)

        storage = self.rl.check_rate_limit('user@example.com', 'storage', now=1000)

        self.assertTrue(storage.allowed)
        self.assertFalse(storage.soft_exceeded)
        self.assertEqual(storage.count, 1)

    def test_export_all_daily_limit_blocks_fourth_request(self) -> None:
        self._fill('user@example.com', 'export_all', 3)

        blocked = self.rl.check_rate_limit('user@example.com', 'export_all', now=1000)

        self.assertFalse(blocked.allowed)
        self.assertTrue(blocked.hard_exceeded)

    def test_rejected_upload_limit_blocks_after_repeated_rejections(self) -> None:
        self._fill('user@example.com', 'rejected_upload', 15)

        blocked = self.rl.check_rate_limit('user@example.com', 'rejected_upload', now=1000)

        self.assertFalse(blocked.allowed)
        self.assertTrue(blocked.hard_exceeded)

    def test_worker_restart_persistence(self) -> None:
        self._fill('user@example.com', 'search', 30)

        self.rl = importlib.reload(self.rl)
        after_restart = self.rl.check_rate_limit('user@example.com', 'search', now=1000)

        self.assertTrue(after_restart.allowed)
        self.assertTrue(after_restart.soft_exceeded)
        self.assertEqual(after_restart.count, 31)


if __name__ == '__main__':
    unittest.main()
