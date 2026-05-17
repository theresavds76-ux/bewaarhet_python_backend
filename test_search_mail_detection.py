from __future__ import annotations

import unittest
from unittest.mock import patch

from bewaarhet.mail_client import IncomingMail
from bewaarhet.processor import process_mail
from bewaarhet.utils import is_probable_search_email


def _mail(subject: str, body: str, *, to_email: str = 'service@bewaarhet.nl') -> IncomingMail:
    return IncomingMail(
        uid='1',
        from_email='user@example.com',
        subject=subject,
        body_text=body,
        date_raw='Sun, 17 May 2026 10:00:00 +0200',
        attachments=[],
        to_email=to_email,
    )


class SearchMailDetectionTests(unittest.TestCase):
    def test_only_explicit_search_subjects_are_search_mail(self) -> None:
        self.assertTrue(is_probable_search_email('zoek', 'rekening vitens', False))
        self.assertTrue(is_probable_search_email('search', 'polis lemonade', False))
        self.assertTrue(is_probable_search_email('zoek: rekening vitens', '', False))
        self.assertTrue(is_probable_search_email('search: polis lemonade', '', False))

    def test_recipient_with_zoek_address_is_search_mail(self) -> None:
        self.assertTrue(
            is_probable_search_email(
                'Rekening Vitens',
                '',
                False,
                'Bewaarhet Zoek <zoek@bewaarhet.nl>',
            )
        )

    def test_document_like_mail_is_not_search_without_explicit_signal(self) -> None:
        body = 'Odido betalingsherinnering. Factuurnummer O-2026-1205. Totaalbedrag EUR 48,50. IBAN NL00BANK0123456789.'
        self.assertFalse(is_probable_search_email('Odido betalingsherinnering', body, False))
        self.assertFalse(is_probable_search_email('Fwd: factuur Vitens', 'Hierbij de rekening.', False))
        self.assertFalse(is_probable_search_email('Nieuwsbrief mei', 'Nieuwe aanbiedingen en updates.', False))

    def test_document_like_mail_without_attachment_continues_to_document_flow(self) -> None:
        mail = _mail(
            'Odido betalingsherinnering',
            'Odido betalingsherinnering. Factuurnummer O-2026-1205. Totaalbedrag EUR 48,50. IBAN NL00BANK0123456789.',
        )

        with (
            patch('bewaarhet.processor.send_search_results') as send_search_results,
            patch('bewaarhet.processor.process_document_body_mail') as process_document_body_mail,
        ):
            process_mail(mail)

        send_search_results.assert_not_called()
        process_document_body_mail.assert_called_once_with(mail)


if __name__ == '__main__':
    unittest.main()
