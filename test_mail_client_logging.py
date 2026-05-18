from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from bewaarhet.mail_client import send_html


class MailClientLoggingTests(unittest.TestCase):
    def test_smtp_success_logs_server_response_and_completion(self) -> None:
        output = StringIO()
        with (
            patch('bewaarhet.mail_client.smtplib.SMTP') as smtp_class,
            redirect_stdout(output),
        ):
            smtp = smtp_class.return_value.__enter__.return_value
            smtp.send_message.return_value = {}

            send_html('user@example.com', 'Onderwerp', '<p>Hoi</p>')

        logs = output.getvalue()
        self.assertIn('SMTP send started | recipient=user@example.com | attachment_count=0', logs)
        self.assertIn('SMTP server response | recipient=user@example.com | refused_recipients={}', logs)
        self.assertIn('SMTP send completed successfully | recipient=user@example.com | duration=', logs)

    def test_smtp_failure_logs_recipient_attachment_count_and_traceback(self) -> None:
        output = StringIO()
        with (
            patch('bewaarhet.mail_client.smtplib.SMTP') as smtp_class,
            redirect_stdout(output),
        ):
            smtp = smtp_class.return_value.__enter__.return_value
            smtp.send_message.side_effect = TimeoutError('timed out')

            with self.assertRaises(TimeoutError):
                send_html('user@example.com', 'Onderwerp', '<p>Hoi</p>')

        logs = output.getvalue()
        self.assertIn('SMTP send failed | recipient=user@example.com | attachment_count=0 | duration=', logs)
        self.assertIn('TimeoutError: timed out', logs)


if __name__ == '__main__':
    unittest.main()
