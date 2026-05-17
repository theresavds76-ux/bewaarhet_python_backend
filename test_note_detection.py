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


if __name__ == '__main__':
    unittest.main()
