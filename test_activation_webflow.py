from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bewaarhet.activation_server import activation_response_for_path, activation_response_for_token
from bewaarhet.customer_onboarding import create_activation_token
from bewaarhet.database import get_customer, init_db, update_customer_status


class TempSettings(SimpleNamespace):
    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


class ActivationWebflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.settings = TempSettings(
            data_dir=root,
            database_path=root / 'bewaarhet.sqlite3',
            backup_dir=root / 'backups',
            log_dir=root / 'logs',
            backup_keep_latest=14,
            public_site_url='https://example.com',
            faq_url='https://example.com/faq',
            activation_url='https://example.com/activeer',
            verification_token_secret='activation-test-secret',
            verification_token_ttl_hours=72,
        )
        self.db_patch = patch('bewaarhet.database.settings', self.settings)
        self.onboarding_patch = patch('bewaarhet.customer_onboarding.settings', self.settings)
        self.web_patch = patch('bewaarhet.activation_server.settings', self.settings)
        self.db_patch.start()
        self.onboarding_patch.start()
        self.web_patch.start()
        init_db()

    def tearDown(self) -> None:
        self.web_patch.stop()
        self.onboarding_patch.stop()
        self.db_patch.stop()
        self.tmp.cleanup()

    def customer_status(self, email: str) -> str | None:
        row = get_customer(email)
        return row['status'] if row else None

    def test_valid_token_activates_customer_and_shows_success_page(self) -> None:
        update_customer_status('valid@example.com', 'pending_verification')
        token = create_activation_token('valid@example.com')

        response = activation_response_for_path(f'/activeer?token={token}')

        self.assertEqual(response.status_code, 200)
        self.assertIn('Je e-mailadres is bevestigd.', response.html)
        self.assertIn('bewaren@bewaarhet.nl', response.html)
        self.assertIn('zoek@bewaarhet.nl', response.html)
        self.assertEqual(self.customer_status('valid@example.com'), 'trial')

    def test_invalid_token_shows_invalid_page_without_stacktrace(self) -> None:
        response = activation_response_for_token('not-a-real-token')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Deze activatielink is ongeldig of verlopen.', response.html)
        self.assertNotIn('Traceback', response.html)

    def test_expired_token_shows_invalid_page(self) -> None:
        update_customer_status('expired@example.com', 'pending_verification')
        token = create_activation_token('expired@example.com', now=1000)

        response = activation_response_for_token(token)

        self.assertEqual(response.status_code, 400)
        self.assertIn('Deze activatielink is ongeldig of verlopen.', response.html)
        self.assertEqual(self.customer_status('expired@example.com'), 'pending_verification')

    def test_reused_token_is_invalid(self) -> None:
        update_customer_status('reuse@example.com', 'pending_verification')
        token = create_activation_token('reuse@example.com')

        first = activation_response_for_token(token)
        second = activation_response_for_token(token)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertIn('Deze activatielink is ongeldig of verlopen.', second.html)
        self.assertEqual(self.customer_status('reuse@example.com'), 'trial')

    def test_missing_token_is_invalid(self) -> None:
        response = activation_response_for_path('/activeer')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Deze activatielink is ongeldig of verlopen.', response.html)


if __name__ == '__main__':
    unittest.main()
