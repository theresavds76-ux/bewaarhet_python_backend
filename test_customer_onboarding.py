from __future__ import annotations

import tempfile
import unittest
import zipfile
from contextlib import closing
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bewaarhet.customer_onboarding import activate_customer_from_token, create_activation_token, verify_activation_token
from bewaarhet.database import get_customer, init_db, update_customer_status
from bewaarhet.mail_client import Attachment, IncomingMail
from bewaarhet.processor import process_upload_mail
from bewaarhet.utils import canonical_customer_identity


def _pdf_attachment(filename: str = 'document.pdf', content: bytes | None = None) -> Attachment:
    payload = content if content is not None else b'%PDF-1.4\nsafe'
    return Attachment(filename=filename, content=payload, content_type='application/pdf', size=len(payload))


def _odt_attachment() -> Attachment:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('mimetype', 'application/vnd.oasis.opendocument.text', compress_type=zipfile.ZIP_STORED)
        archive.writestr('content.xml', b'<document>safe</document>')
        archive.writestr('META-INF/manifest.xml', b'<manifest />')
    payload = buffer.getvalue()
    return Attachment(filename='document.odt', content=payload, content_type='application/vnd.oasis.opendocument.text', size=len(payload))


def _mail(att: Attachment, *, sender: str = 'New.User@Example.COM') -> IncomingMail:
    return IncomingMail(
        uid='customer-1',
        from_email=sender,
        subject='Factuur test',
        body_text='Bijgevoegd.',
        date_raw='Thu, 21 May 2026 10:00:00 +0200',
        attachments=[att],
        to_email='bewaren@bewaarhet.nl',
    )


class TempSettings(SimpleNamespace):
    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


class CustomerOnboardingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.settings = TempSettings(
            data_dir=root,
            database_path=root / 'bewaarhet.sqlite3',
            backup_dir=root / 'backups',
            log_dir=root / 'logs',
            backup_keep_latest=14,
            max_attachment_mb=15,
            customer_onboarding_enabled=True,
            allowed_extensions={'.pdf', '.jpg', '.jpeg', '.png', '.odt'},
            trial_allowed_extensions={'.pdf', '.jpg', '.jpeg', '.png'},
            max_trial_documents=2,
            max_trial_storage_mb=1,
            max_trial_file_size_mb=1,
            max_trial_mails_per_hour=20,
            max_trial_documents_per_day=25,
            welcome_email_subject='Welkom bij Bewaarhet',
            public_site_url='https://example.com',
            activation_url='https://example.com/activeer',
            faq_url='https://example.com/faq',
            verification_token_secret='unit-test-secret',
            verification_token_ttl_hours=72,
            dropbox_base_path='/Bewaar het/Klanten',
            openai_api_key='',
            openai_model='gpt-5-mini',
        )
        self.db_patch = patch('bewaarhet.database.settings', self.settings)
        self.processor_patch = patch('bewaarhet.processor.settings', self.settings)
        self.onboarding_patch = patch('bewaarhet.customer_onboarding.settings', self.settings)
        self.classifier_patch = patch('bewaarhet.classifier.settings', self.settings)
        self.db_patch.start()
        self.processor_patch.start()
        self.onboarding_patch.start()
        self.classifier_patch.start()
        init_db()

    def customer(self, email: str) -> dict | None:
        row = get_customer(email)
        return dict(row) if row else None

    def document_count(self) -> int:
        from bewaarhet.database import connect

        with closing(connect()) as conn:
            return int(conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0])

    def tearDown(self) -> None:
        self.classifier_patch.stop()
        self.onboarding_patch.stop()
        self.processor_patch.stop()
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_first_unknown_sender_creates_pending_verification_account(self) -> None:
        with (
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.rate_limiter.send_html'),
            patch('bewaarhet.processor.ocr_space', return_value='Factuur test') as ocr_space,
            patch('bewaarhet.processor.upload_file') as upload_file,
        ):
            process_upload_mail(_mail(_pdf_attachment()))

        customer = self.customer('new.user@example.com')
        self.assertIsNotNone(customer)
        self.assertEqual(customer['email'], 'new.user@example.com')
        self.assertEqual(customer['status'], 'pending_verification')
        self.assertEqual(customer['document_count'], 0)
        self.assertEqual(self.document_count(), 0)
        send_html.assert_called_once()
        welcome_body = send_html.call_args.args[2]
        self.assertIn('gratis proefomgeving', welcome_body)
        self.assertIn('token=', welcome_body)
        self.assertNotIn('Reageer', welcome_body)
        ocr_space.assert_not_called()
        upload_file.assert_not_called()

    def test_activation_token_starts_trial(self) -> None:
        update_customer_status('verify@example.com', 'pending_verification')
        token = create_activation_token('verify@example.com')

        self.assertEqual(verify_activation_token(token), 'verify@example.com')
        customer = activate_customer_from_token(token)

        self.assertEqual(customer['status'], 'trial')
        self.assertIsNotNone(customer['trial_started_at'])

    def test_activation_token_expires(self) -> None:
        token = create_activation_token('expired@example.com', now=1000)

        with self.assertRaises(ValueError):
            verify_activation_token(token, now=1000 + 73 * 3600)

    def test_upload_after_activation_is_processed(self) -> None:
        update_customer_status('active-trial@example.com', 'trial')

        with (
            patch('bewaarhet.processor.send_html'),
            patch('bewaarhet.rate_limiter.send_html'),
            patch('bewaarhet.processor.ocr_space', return_value='Factuur test') as ocr_space,
            patch('bewaarhet.processor.upload_file') as upload_file,
        ):
            process_upload_mail(_mail(_pdf_attachment(), sender='active-trial@example.com'))

        customer = self.customer('active-trial@example.com')
        self.assertEqual(customer['status'], 'trial')
        self.assertEqual(customer['document_count'], 1)
        ocr_space.assert_called_once()
        upload_file.assert_called_once()

    def test_pending_user_gets_reminder_only_on_followup(self) -> None:
        update_customer_status('pending@example.com', 'pending_verification')

        with (
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.rate_limiter.send_html'),
            patch('bewaarhet.processor.ocr_space') as ocr_space,
            patch('bewaarhet.processor.upload_file') as upload_file,
        ):
            process_upload_mail(_mail(_pdf_attachment(), sender='pending@example.com'))

        send_html.assert_called_once()
        self.assertIn('Bevestig eerst je e-mailadres', send_html.call_args.args[2])
        ocr_space.assert_not_called()
        upload_file.assert_not_called()

    def test_trial_document_limit_blocks_before_ocr(self) -> None:
        update_customer_status('limit@example.com', 'trial')
        # Set the counter directly through the same database to simulate an exhausted trial.
        from bewaarhet.database import connect

        with closing(connect()) as conn:
            conn.execute("UPDATE customers SET document_count = 2 WHERE email = 'limit@example.com'")
            conn.commit()

        with (
            patch('bewaarhet.processor.send_html'),
            patch('bewaarhet.rate_limiter.send_html'),
            patch('bewaarhet.processor.ocr_space') as ocr_space,
            patch('bewaarhet.processor.upload_file') as upload_file,
        ):
            process_upload_mail(_mail(_pdf_attachment(), sender='limit@example.com'))

        ocr_space.assert_not_called()
        upload_file.assert_not_called()

    def test_rate_limit_blocks_before_ocr(self) -> None:
        update_customer_status('busy@example.com', 'trial')

        with (
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=False),
            patch('bewaarhet.processor.send_html'),
            patch('bewaarhet.processor.ocr_space') as ocr_space,
            patch('bewaarhet.processor.upload_file') as upload_file,
        ):
            process_upload_mail(_mail(_pdf_attachment(), sender='busy@example.com'))

        ocr_space.assert_not_called()
        upload_file.assert_not_called()

    def test_blocked_user_is_rejected_before_ocr(self) -> None:
        update_customer_status('blocked@example.com', 'blocked')

        with (
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.ocr_space') as ocr_space,
            patch('bewaarhet.processor.upload_file') as upload_file,
        ):
            process_upload_mail(_mail(_pdf_attachment(), sender='blocked@example.com'))

        send_html.assert_called_once()
        ocr_space.assert_not_called()
        upload_file.assert_not_called()

    def test_active_user_keeps_full_allowed_upload_flow(self) -> None:
        update_customer_status('active@example.com', 'active')

        with (
            patch('bewaarhet.processor.send_html'),
            patch('bewaarhet.rate_limiter.send_html'),
            patch('bewaarhet.processor.ocr_space', return_value='Factuur test') as ocr_space,
            patch('bewaarhet.processor.upload_file') as upload_file,
        ):
            process_upload_mail(_mail(_odt_attachment(), sender='active@example.com'))

        customer = self.customer('active@example.com')
        self.assertEqual(customer['status'], 'active')
        self.assertEqual(customer['document_count'], 1)
        ocr_space.assert_called_once()
        upload_file.assert_called_once()

    def test_trial_filetype_filter_blocks_odt_before_ocr(self) -> None:
        update_customer_status('trial@example.com', 'trial')

        with (
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.rate_limiter.send_html'),
            patch('bewaarhet.processor.ocr_space') as ocr_space,
            patch('bewaarhet.processor.upload_file') as upload_file,
        ):
            process_upload_mail(_mail(_odt_attachment(), sender='trial@example.com'))

        customer = self.customer('trial@example.com')
        self.assertEqual(customer['status'], 'trial')
        self.assertGreaterEqual(send_html.call_count, 1)
        ocr_space.assert_not_called()
        upload_file.assert_not_called()

    def test_email_normalization(self) -> None:
        self.assertEqual(canonical_customer_identity(' User@Example.COM '), 'user@example.com')
        update_customer_status(' User@Example.COM ', 'active')

        customer = self.customer('user@example.com')
        self.assertEqual(customer['email'], 'user@example.com')
        self.assertEqual(customer['status'], 'active')

    def test_fake_pdf_mismatch_is_rejected_before_ocr(self) -> None:
        update_customer_status('fake@example.com', 'trial')

        with (
            patch('bewaarhet.processor.send_html'),
            patch('bewaarhet.rate_limiter.send_html'),
            patch('bewaarhet.processor.ocr_space') as ocr_space,
            patch('bewaarhet.processor.upload_file') as upload_file,
        ):
            process_upload_mail(_mail(_pdf_attachment(content=b'MZ executable'), sender='fake@example.com'))

        ocr_space.assert_not_called()
        upload_file.assert_not_called()


if __name__ == '__main__':
    unittest.main()
