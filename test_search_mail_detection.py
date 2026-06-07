from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
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


def _mail_from(
    subject: str,
    body: str,
    *,
    from_email: str,
    to_email: str,
) -> IncomingMail:
    mail = _mail(subject, body, to_email=to_email)
    mail.from_email = from_email
    return mail


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

    def test_mail_to_bewaren_without_attachment_is_saved(self) -> None:
        mail = _mail(
            'Los document',
            'Bewaar deze notitie voor later.',
            to_email='Bewaarhet <bewaren@bewaarhet.nl>',
        )

        with (
            patch('bewaarhet.processor.send_search_results') as send_search_results,
            patch('bewaarhet.processor.process_document_body_mail') as process_document_body_mail,
        ):
            process_mail(mail)

        send_search_results.assert_not_called()
        process_document_body_mail.assert_called_once_with(mail)

    def test_mail_to_bewaren_always_stores_even_with_search_words(self) -> None:
        mail = _mail(
            'Ik zoek mijn wachtwoord',
            'wachtwoord AAA',
            to_email='Bewaarhet <bewaren@bewaarhet.nl>',
        )

        output = StringIO()
        with (
            patch('bewaarhet.processor.send_search_results') as send_search_results,
            patch('bewaarhet.processor.process_document_body_mail') as process_document_body_mail,
            redirect_stdout(output),
        ):
            process_mail(mail)

        send_search_results.assert_not_called()
        process_document_body_mail.assert_called_once_with(mail)
        self.assertIn('Route gekozen: store | Reden: ontvanger bevat bewaren@bewaarhet.nl', output.getvalue())

    def test_mail_to_bewaren_with_empty_subject_is_saved(self) -> None:
        mail = _mail(
            '',
            'Korte tekst die toch bewaard moet worden.',
            to_email='bewaren@bewaarhet.nl',
        )

        with patch('bewaarhet.processor.process_document_body_mail') as process_document_body_mail:
            process_mail(mail)

        process_document_body_mail.assert_called_once_with(mail)

    def test_mail_to_bewaren_from_external_sender_is_saved(self) -> None:
        mail = _mail_from(
            '',
            'Externe mail zonder bijlage.',
            from_email='klant@extern-bedrijf.nl',
            to_email='bewaren@bewaarhet.nl',
        )

        with patch('bewaarhet.processor.process_document_body_mail') as process_document_body_mail:
            process_mail(mail)

        process_document_body_mail.assert_called_once_with(mail)

    def test_mail_to_zoek_address_becomes_search(self) -> None:
        mail = _mail(
            'factuur kpn',
            'april 2026',
            to_email='Bewaarhet Zoek <zoek@bewaarhet.nl>',
        )

        with (
            patch('bewaarhet.processor.process_document_body_mail') as process_document_body_mail,
            patch('bewaarhet.processor.send_search_results') as send_search_results,
            patch('bewaarhet.processor.send_html') as send_html,
        ):
            process_mail(mail)

        process_document_body_mail.assert_not_called()
        send_search_results.assert_called_once_with('user@example.com', 'factuur kpn\napril 2026')
        send_html.assert_not_called()

    def test_mail_to_zoek_address_always_searches_even_with_invoice_content(self) -> None:
        mail = _mail(
            'Odido betalingsherinnering',
            'Factuurnummer O-2026-1205. Totaalbedrag EUR 48,50.',
            to_email='zoek@bewaarhet.nl',
        )

        output = StringIO()
        with (
            patch('bewaarhet.processor.process_document_body_mail') as process_document_body_mail,
            patch('bewaarhet.processor.send_search_results') as send_search_results,
            redirect_stdout(output),
        ):
            process_mail(mail)

        process_document_body_mail.assert_not_called()
        send_search_results.assert_called_once_with(
            'user@example.com',
            'Odido betalingsherinnering\nFactuurnummer O-2026-1205. Totaalbedrag EUR 48,50.',
        )
        self.assertIn('Route gekozen: search | Reden: ontvanger bevat zoek@bewaarhet.nl', output.getvalue())

    def test_service_search_intent_becomes_search(self) -> None:
        mail = _mail(
            'Ik zoek mn wachtwoord voor AAA',
            '',
            to_email='service@bewaarhet.nl',
        )

        output = StringIO()
        with (
            patch('bewaarhet.processor.process_document_body_mail') as process_document_body_mail,
            patch('bewaarhet.processor.send_search_results') as send_search_results,
            redirect_stdout(output),
        ):
            process_mail(mail)

        process_document_body_mail.assert_not_called()
        send_search_results.assert_called_once_with('user@example.com', 'wachtwoord AAA')
        self.assertIn('Route gekozen: search | Reden: service@bewaarhet.nl met zoekintentie', output.getvalue())

    def test_service_stuur_mijn_factuur_becomes_search(self) -> None:
        mail = _mail(
            'Stuur mijn factuur van KPN',
            '',
            to_email='service@bewaarhet.nl',
        )

        with (
            patch('bewaarhet.processor.process_document_body_mail') as process_document_body_mail,
            patch('bewaarhet.processor.send_search_results') as send_search_results,
        ):
            process_mail(mail)

        process_document_body_mail.assert_not_called()
        send_search_results.assert_called_once_with('user@example.com', 'factuur KPN')

    def test_service_bon_ikea_2024_without_search_verb_is_stored(self) -> None:
        mail = _mail(
            'bon ikea 2024',
            'Ter opslag.',
            to_email='service@bewaarhet.nl',
        )

        with (
            patch('bewaarhet.processor.process_document_body_mail') as process_document_body_mail,
            patch('bewaarhet.processor.send_search_results') as send_search_results,
        ):
            process_mail(mail)

        send_search_results.assert_not_called()
        process_document_body_mail.assert_called_once_with(mail)

    def test_service_normal_invoice_reminder_becomes_store(self) -> None:
        mail = _mail(
            'Odido betalingsherinnering',
            'Factuurnummer O-2026-1205. Totaalbedrag EUR 48,50. IBAN NL00BANK0123456789.',
            to_email='service@bewaarhet.nl',
        )

        output = StringIO()
        with (
            patch('bewaarhet.processor.send_search_results') as send_search_results,
            patch('bewaarhet.processor.process_document_body_mail') as process_document_body_mail,
            redirect_stdout(output),
        ):
            process_mail(mail)

        send_search_results.assert_not_called()
        process_document_body_mail.assert_called_once_with(mail)
        self.assertIn('Route gekozen: store | Reden: service@bewaarhet.nl zonder zoekintentie', output.getvalue())

    def test_subject_zoek_still_works_as_fallback(self) -> None:
        mail = _mail(
            'zoek',
            'factuur kpn april',
            to_email='info@bewaarhet.nl',
        )

        with patch('bewaarhet.processor.send_search_results') as send_search_results:
            process_mail(mail)

        send_search_results.assert_called_once_with('user@example.com', 'factuur kpn april')

    def test_non_bewaarhet_recipient_is_ignored_even_if_document_like(self) -> None:
        mail = _mail_from(
            'EaseFlow Leadrapport - 2026-06-08',
            'Orderverwerking, factureren en facturatie komen voor in dit rapport.',
            from_email='theresa@youandigoods.nl',
            to_email='theresa@easeflow.nl',
        )

        output = StringIO()
        with (
            patch('bewaarhet.processor.process_document_body_mail') as process_document_body_mail,
            patch('bewaarhet.processor.process_upload_mail') as process_upload_mail,
            patch('bewaarhet.processor.send_search_results') as send_search_results,
            redirect_stdout(output),
        ):
            handled = process_mail(mail)

        self.assertFalse(handled)
        process_document_body_mail.assert_not_called()
        process_upload_mail.assert_not_called()
        send_search_results.assert_not_called()
        self.assertIn('Mail buiten Bewaarhet-scope genegeerd', output.getvalue())

    def test_factureren_and_facturatie_are_not_invoice_signals(self) -> None:
        self.assertFalse(
            is_probable_search_email(
                'EaseFlow Leadrapport',
                'Dit rapport noemt orderverwerking, factureren en facturatie, maar bevat geen betaaldocument.',
                False,
                'theresa@easeflow.nl',
            )
        )
        mail = _mail(
            'EaseFlow Leadrapport',
            'Dit rapport noemt orderverwerking, factureren en facturatie zonder echte betaalgegevens.',
            to_email='service@bewaarhet.nl',
        )
        from bewaarhet.utils import is_document_email_without_attachment

        self.assertFalse(is_document_email_without_attachment(mail))


if __name__ == '__main__':
    unittest.main()
