from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from bewaarhet.classifier import classify_document
from bewaarhet.mail_client import IncomingMail
from bewaarhet.processor import process_mail
from bewaarhet.utils import (
    detect_purpose,
    generate_filename,
    is_note_like_content,
    strip_email_signature,
)


def _mail(subject: str, body: str, *, to_email: str = 'bewaren@bewaarhet.nl') -> IncomingMail:
    return IncomingMail(
        uid='note-1',
        from_email='remco@vdsintl.nl',
        subject=subject,
        body_text=body,
        date_raw='Sun, 17 May 2026 10:00:00 +0200',
        attachments=[],
        to_email=to_email,
    )


class NoteDetectionTests(unittest.TestCase):
    def test_note_phrase_classifies_as_note(self) -> None:
        body = 'Bewaar deze notitie voor me:\n\nWachtwoord voor AAA is AAEUUUE!'

        self.assertEqual(classify_document(body, 'email_body.pdf', '', body[:200]), 'notities')
        self.assertEqual(detect_purpose(body, '', 'email_body.pdf'), 'notitie')

    def test_note_filename_uses_context_not_supplier(self) -> None:
        body = 'Bewaar deze notitie voor me:\n\nWachtwoord voor AAA is AAEUUUE!'

        filename, document_date = generate_filename(
            'notities',
            'email_body.pdf',
            body,
            '2026-05-17',
            '',
            supplier='vdsintl',
            purpose='notitie',
        )

        self.assertEqual(document_date, '2026-05-17')
        self.assertEqual(filename, 'notitie_wachtwoord_aaa_17-05-2026.pdf')

    def test_note_beats_certificate_text_in_signature(self) -> None:
        body = (
            'Bewaar deze notitie voor me:\n\n'
            'Wachtwoord voor AAA is AAEUUUE!\n\n'
            'Met vriendelijke groet,\n'
            'VDSINTL B.V.\n'
            'Certificate of Compliance available on request.'
        )

        stripped, ignored = strip_email_signature(body)

        self.assertGreater(ignored, 0)
        self.assertNotIn('Certificate of Compliance', stripped)
        self.assertEqual(detect_purpose(body, '', 'email_body.pdf'), 'notitie')

    def test_regular_certificate_detection_still_works(self) -> None:
        body = 'Certificate of Compliance\nManufacturer: Example BV\nProduct name: Smart lock'

        self.assertEqual(detect_purpose(body, '', 'certificate.pdf'), 'coc')

    def test_body_note_mail_is_saved_as_notitie_with_semantic_logs(self) -> None:
        mail = _mail(
            '',
            (
                'Bewaar deze notitie voor me:\n\n'
                'Wachtwoord voor AAA is AAEUUUE!\n\n'
                'Met vriendelijke groet,\n'
                'VDSINTL B.V.\n'
                'Certificate of Compliance available on request.'
            ),
        )

        output = StringIO()
        with (
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.add_document') as add_document,
            patch(
                'bewaarhet.processor._resolve_filename_collision',
                side_effect=lambda _customer, _category, filename: filename,
            ),
            redirect_stdout(output),
        ):
            process_mail(mail)

        record = add_document.call_args.args[0]
        self.assertEqual(record['category'], 'notities')
        self.assertEqual(record['purpose'], 'notitie')
        self.assertEqual(record['supplier'], '')
        self.assertEqual(record['filename'], 'notitie_wachtwoord_aaa_17-05-2026.pdf')
        self.assertIn('/notities/notitie_wachtwoord_aaa_17-05-2026.pdf', upload_file.call_args.args[1])
        self.assertIn('Route gekozen: store | Reden: ontvanger bevat bewaren@bewaarhet.nl', output.getvalue())
        self.assertIn('[semantic-debug] detected semantic type: notitie', output.getvalue())
        self.assertIn('[semantic-debug] ignored signature/footer length:', output.getvalue())
        self.assertIn('[storage-debug] customer_email: remco@vdsintl.nl', output.getvalue())
        self.assertIn('[storage-debug] safe_customer_folder: remco_at_vdsintl.nl', output.getvalue())
        self.assertIn('[storage-debug] category: notities', output.getvalue())
        self.assertIn('[storage-debug] ocr_preview length:', output.getvalue())
        self.assertIn('[storage-debug] ocr_text length:', output.getvalue())
        self.assertIn('[storage-debug] sanitized searchable preview:', output.getvalue())
        self.assertNotIn('AAEUUUE', output.getvalue())

    def test_implicit_body_note_mail_is_saved_as_notitie(self) -> None:
        mail = _mail('', 'Wachtwoord AAA: AAEUUUE')

        with (
            patch('bewaarhet.processor.upload_file'),
            patch('bewaarhet.processor.add_document') as add_document,
            patch(
                'bewaarhet.processor._resolve_filename_collision',
                side_effect=lambda _customer, _category, filename: filename,
            ),
        ):
            process_mail(mail)

        record = add_document.call_args.args[0]
        self.assertEqual(record['category'], 'notities')
        self.assertEqual(record['purpose'], 'notitie')
        self.assertTrue(record['filename'].startswith('notitie_'))

    def test_subject_notitie_short_password_body_is_saved_as_notitie(self) -> None:
        mail = _mail('notitie', 'wachtwoord RepelsteeltjeA13+')

        with (
            patch('bewaarhet.processor.upload_file'),
            patch('bewaarhet.processor.add_document') as add_document,
            patch(
                'bewaarhet.processor._resolve_filename_collision',
                side_effect=lambda _customer, _category, filename: filename,
            ),
        ):
            process_mail(mail)

        record = add_document.call_args.args[0]
        self.assertEqual(record['category'], 'notities')
        self.assertEqual(record['purpose'], 'notitie')
        self.assertEqual(record['filename'], 'notitie_wachtwoord_17-05-2026.pdf')

    def test_subject_note_word_forces_note_detection(self) -> None:
        body = 'wachtwoord RepelsteeltjeA13+'

        self.assertTrue(is_note_like_content(body, 'notitie', 'email_body.pdf'))
        self.assertEqual(classify_document(body, 'email_body.pdf', 'notitie', body[:200]), 'notities')
        self.assertEqual(detect_purpose(body, 'notitie', 'email_body.pdf'), 'notitie')

    def test_implicit_password_text_becomes_note(self) -> None:
        body = 'Wachtwoord AAA: AAEUUUE'

        self.assertTrue(is_note_like_content(body))
        self.assertEqual(classify_document(body, 'email_body.pdf', '', body[:200]), 'notities')
        self.assertEqual(detect_purpose(body, '', 'email_body.pdf'), 'notitie')

    def test_short_bare_password_text_becomes_note(self) -> None:
        body = 'wachtwoord RepelsteeltjeA13+'

        self.assertTrue(is_note_like_content(body))
        self.assertEqual(classify_document(body, 'email_body.pdf', '', body[:200]), 'notities')
        self.assertEqual(detect_purpose(body, '', 'email_body.pdf'), 'notitie')

        filename, _document_date = generate_filename(
            'notities',
            'email_body.pdf',
            body,
            '2026-05-17',
            '',
            supplier='youandigoods',
            purpose='notitie',
        )
        self.assertEqual(filename, 'notitie_wachtwoord_17-05-2026.pdf')

    def test_implicit_login_text_becomes_note(self) -> None:
        body = 'Login Bol: gebruiker test / wachtwoord xyz'

        self.assertTrue(is_note_like_content(body))
        self.assertEqual(classify_document(body, 'email_body.pdf', '', body[:200]), 'notities')
        self.assertEqual(detect_purpose(body, '', 'email_body.pdf'), 'notitie')

    def test_implicit_code_text_becomes_note(self) -> None:
        body = 'Code voordeur: 1234'

        self.assertTrue(is_note_like_content(body))
        self.assertEqual(classify_document(body, 'email_body.pdf', '', body[:200]), 'notities')
        self.assertEqual(detect_purpose(body, '', 'email_body.pdf'), 'notitie')

    def test_implicit_iban_reference_becomes_note(self) -> None:
        body = 'IBAN oma: NL12BANK0123456789'

        self.assertTrue(is_note_like_content(body))
        self.assertEqual(classify_document(body, 'email_body.pdf', '', body[:200]), 'notities')
        self.assertEqual(detect_purpose(body, '', 'email_body.pdf'), 'notitie')

    def test_implicit_vergeet_niet_reminder_becomes_note(self) -> None:
        body = 'Vergeet niet tandarts bellen dinsdag'

        self.assertTrue(is_note_like_content(body))
        self.assertEqual(classify_document(body, 'email_body.pdf', '', body[:200]), 'notities')
        self.assertEqual(detect_purpose(body, '', 'email_body.pdf'), 'notitie')

    def test_invoice_footer_password_text_does_not_become_note(self) -> None:
        body = (
            'Factuur KPN\n'
            'Factuurnummer: KPN-2026-05\n'
            'Totaalbedrag: EUR 42,00\n\n'
            'Wachtwoord vergeten? Klik hier om uw account te herstellen.'
        )

        self.assertFalse(is_note_like_content(body))
        self.assertNotEqual(classify_document(body, 'factuur_kpn.pdf', 'Factuur KPN', body[:200]), 'notities')
        self.assertNotEqual(detect_purpose(body, 'Factuur KPN', 'factuur_kpn.pdf'), 'notitie')

    def test_bank_statement_rekeningnummer_does_not_become_note(self) -> None:
        body = (
            'ING Rekeningafschrift\n'
            'Rekeningnummer: NL91 INGB 0001 2345 67\n'
            'Periode: 01-06-2025 tot 30-06-2025\n'
            'Saldo: EUR 5.234,56'
        )

        self.assertFalse(is_note_like_content(body, 'ING rekeningafschrift', 'bankafschrift juni.pdf'))
        self.assertNotEqual(
            classify_document(body, 'bankafschrift juni.pdf', 'ING rekeningafschrift', body[:200]),
            'notities',
        )

    def test_payment_instruction_iban_does_not_become_note(self) -> None:
        body = (
            'Betaalopdracht\n'
            'Begunstigde: Elektriciteit Bedrijf\n'
            'IBAN: NL91 INGB 0002 3456 78\n'
            'Bedrag: EUR 250.00'
        )

        self.assertFalse(is_note_like_content(body, 'betaalopdracht', 'betaalopdracht.pdf'))
        self.assertNotEqual(classify_document(body, 'betaalopdracht.pdf', 'betaalopdracht', body[:200]), 'notities')


if __name__ == '__main__':
    unittest.main()
