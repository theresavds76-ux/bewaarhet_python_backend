from __future__ import annotations

import os
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from bewaarhet.processor import _log_supplier_debug
from bewaarhet.utils import sanitize_for_log


class LogSanitizationTests(unittest.TestCase):
    def test_masks_password_like_values(self) -> None:
        self.assertEqual(
            sanitize_for_log('wachtwoord ABC123'),
            'wachtwoord [REDACTED]',
        )
        self.assertEqual(
            sanitize_for_log('password: hello123'),
            'password: [REDACTED]',
        )
        self.assertEqual(
            sanitize_for_log('pincode 1234'),
            'pincode [REDACTED]',
        )

    def test_masks_iban_like_values(self) -> None:
        self.assertEqual(
            sanitize_for_log('IBAN NL91ABNA0417164300'),
            'IBAN NL91********4300',
        )
        self.assertEqual(
            sanitize_for_log('Rekening NL91 ABNA 0417 1643 00'),
            'Rekening NL91********4300',
        )

    def test_hides_links_and_configured_tokens(self) -> None:
        with patch.dict(
            os.environ,
            {
                'OPENAI_API_KEY': 'sk-secret-test-key',
                'DROPBOX_REFRESH_TOKEN': 'dropbox-refresh-token',
                'ZOHO_APP_PASSWORD': 'zoho-password-value',
            },
        ):
            sanitized = sanitize_for_log(
                'url=https://dl.dropboxusercontent.com/tmp/file.pdf '
                'openai=sk-secret-test-key '
                'bare_openai=sk-proj-abcdefghijklmnopqrstuvwxyz '
                'bare_dropbox=sl.abcdefghijklmnopqrstuvwxyz123456 '
                'dropbox=dropbox-refresh-token '
                'zoho=zoho-password-value '
                'access_token=abc123456789'
            )

        self.assertIn('[LINK REDACTED]', sanitized)
        self.assertIn('openai=[SECRET REDACTED]', sanitized)
        self.assertIn('dropbox=[SECRET REDACTED]', sanitized)
        self.assertIn('zoho=[SECRET REDACTED]', sanitized)
        self.assertIn('access_token=[SECRET REDACTED]', sanitized)
        self.assertNotIn('dl.dropboxusercontent.com', sanitized)
        self.assertNotIn('sk-secret-test-key', sanitized)
        self.assertNotIn('sk-proj-abcdefghijklmnopqrstuvwxyz', sanitized)
        self.assertNotIn('sl.abcdefghijklmnopqrstuvwxyz123456', sanitized)
        self.assertNotIn('dropbox-refresh-token', sanitized)
        self.assertNotIn('zoho-password-value', sanitized)
        self.assertNotIn('abc123456789', sanitized)

    def test_ocr_debug_preview_is_sanitized_and_truncated(self) -> None:
        secret_tail = 'x' * 120
        output = StringIO()
        with redirect_stdout(output):
            _log_supplier_debug(
                original_filename='note.pdf',
                mail_subject='notitie',
                sender_email='user@example.com',
                ocr_text=f'Wachtwoord voor AAA is AAEUUUE! {secret_tail}',
                supplier='',
                purpose='notitie',
                generated_filename='notitie_wachtwoord_aaa_17-05-2026.pdf',
            )

        logs = output.getvalue()
        preview_line = next(
            line for line in logs.splitlines()
            if line.startswith('[supplier-debug] sanitized OCR preview:')
        )
        preview = preview_line.split(': ', 1)[1]
        self.assertLessEqual(len(preview), 100)
        self.assertIn('Wachtwoord voor AAA is [REDACTED]', preview)
        self.assertNotIn('AAEUUUE', logs)
        self.assertNotIn(secret_tail, logs)


if __name__ == '__main__':
    unittest.main()
