from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bewaarhet.mail_client import Attachment, IncomingMail
from bewaarhet.processor import _is_allowed, _too_large, process_upload_mail


ALLOWED_EXTENSIONS = {
    '.pdf', '.jpg', '.jpeg', '.png', '.heic',
    '.doc', '.docx', '.odt',
    '.xls', '.xlsx', '.ods', '.csv',
    '.txt', '.rtf',
    '.ppt', '.pptx', '.odp',
    '.zip',
}


def _attachment(filename: str, size: int = 100, content: bytes | None = None) -> Attachment:
    return Attachment(
        filename=filename,
        content=content if content is not None else b'x' * size,
        content_type='application/octet-stream',
        size=size,
    )


def _mail(att: Attachment) -> IncomingMail:
    return IncomingMail(
        uid='1',
        from_email='user@example.com',
        subject='Huurovereenkomst Cazas Wonen',
        body_text='Bijgevoegd het huurcontract voor je woning.',
        date_raw='Sun, 17 May 2026 10:00:00 +0200',
        attachments=[att],
    )


class AllowedFilesTests(unittest.TestCase):
    def test_odt_allowed(self) -> None:
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS, max_attachment_mb=15)):
            self.assertTrue(_is_allowed(_attachment('document.odt')))

    def test_ods_allowed(self) -> None:
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS, max_attachment_mb=15)):
            self.assertTrue(_is_allowed(_attachment('sheet.ods')))

    def test_zip_allowed_up_to_15_mb(self) -> None:
        size = 15 * 1024 * 1024
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS, max_attachment_mb=15)):
            att = _attachment('archive.zip', size=size, content=b'zip')
            self.assertTrue(_is_allowed(att))
            self.assertFalse(_too_large(att))

    def test_zip_over_15_mb_rejected(self) -> None:
        size = 15 * 1024 * 1024 + 1
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS, max_attachment_mb=15)):
            att = _attachment('archive.zip', size=size, content=b'zip')
            self.assertTrue(_is_allowed(att))
            self.assertTrue(_too_large(att))

    def test_mp4_rejected(self) -> None:
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS | {'.mp4'}, max_attachment_mb=15)):
            self.assertFalse(_is_allowed(_attachment('video.mp4')))

    def test_generic_zip_gets_semantic_filename_from_context(self) -> None:
        att = _attachment('1234.zip', content=b'zip-bytes')
        mail = _mail(att)

        with (
            patch('bewaarhet.processor.ocr_space') as ocr_space,
            patch('bewaarhet.processor._resolve_filename_collision', side_effect=lambda _customer, _category, filename: filename),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.add_document') as add_document,
            patch('bewaarhet.processor.settings', SimpleNamespace(
                allowed_extensions=ALLOWED_EXTENSIONS,
                max_attachment_mb=15,
                dropbox_base_path='/Bewaar het/Klanten',
            )),
        ):
            process_upload_mail(mail)

        ocr_space.assert_not_called()
        upload_file.assert_called_once()
        add_document.assert_called_once()
        record = add_document.call_args.args[0]
        self.assertTrue(record['filename'].endswith('.zip'))
        self.assertNotIn('1234', record['filename'])
        self.assertIn('contract', record['filename'])
        self.assertIn('cazas_wonen', record['filename'])
        self.assertIn('Huurovereenkomst Cazas Wonen', record['ocr_preview'])
        self.assertIn('huurcontract', record['ocr_text'])


if __name__ == '__main__':
    unittest.main()
