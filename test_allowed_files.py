from __future__ import annotations

import unittest
import zipfile
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from bewaarhet.mail_client import Attachment, IncomingMail
from bewaarhet.processor import (
    SAFE_ALLOWED_EXTENSIONS,
    _is_allowed,
    _prepare_customer_for_storage,
    _too_large,
    _validate_attachment,
    process_upload_mail,
)


ALLOWED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.odt',
    '.xls', '.xlsx', '.ods', '.txt', '.csv', '.rtf',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff',
    '.zip', '.rar', '.7z', '.tar', '.gz',
}

TRIAL_ALLOWED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.odt',
    '.xls', '.xlsx', '.ods', '.txt', '.csv', '.rtf',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff',
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


def _zip_bytes(files: dict[str, bytes] | None = None) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in (files or {'document.txt': b'hello'}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _odf_bytes(mimetype: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('mimetype', mimetype, compress_type=zipfile.ZIP_STORED)
        archive.writestr('content.xml', b'<document>safe</document>')
        archive.writestr('META-INF/manifest.xml', b'<manifest />')
    return buffer.getvalue()


class AllowedFilesTests(unittest.TestCase):
    def test_odt_allowed(self) -> None:
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS, max_attachment_mb=15)):
            self.assertTrue(_is_allowed(_attachment('document.odt', content=_odf_bytes('application/vnd.oasis.opendocument.text'))))

    def test_ods_allowed(self) -> None:
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS, max_attachment_mb=15)):
            self.assertTrue(_is_allowed(_attachment('sheet.ods', content=_odf_bytes('application/vnd.oasis.opendocument.spreadsheet'))))

    def test_rtf_allowed(self) -> None:
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS, max_attachment_mb=15)):
            self.assertTrue(_is_allowed(_attachment('note.rtf', content=b'{\\rtf1 safe}')))

    def test_docm_rejected(self) -> None:
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS | {'.docm'}, max_attachment_mb=15)):
            self.assertFalse(_is_allowed(_attachment('macro.docm')))

    def test_xlsm_rejected(self) -> None:
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS | {'.xlsm'}, max_attachment_mb=15)):
            self.assertFalse(_is_allowed(_attachment('macro.xlsm')))

    def test_unknown_extension_rejected(self) -> None:
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS | {'.madeup'}, max_attachment_mb=15)):
            self.assertFalse(_is_allowed(_attachment('document.madeup')))

    def test_unvalidated_archives_rejected_even_if_configured(self) -> None:
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS, max_attachment_mb=15)):
            self.assertFalse(_is_allowed(_attachment('archive.rar')))
            self.assertFalse(_is_allowed(_attachment('archive.7z')))
            self.assertFalse(_is_allowed(_attachment('archive.tar')))
            self.assertFalse(_is_allowed(_attachment('archive.gz')))

    def test_zip_allowed_up_to_15_mb(self) -> None:
        size = 15 * 1024 * 1024
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS, max_attachment_mb=15)):
            content = _zip_bytes()
            att = _attachment('archive.zip', size=size, content=content)
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

    def test_default_safe_extensions_match_trial_allowlist(self) -> None:
        self.assertEqual(TRIAL_ALLOWED_EXTENSIONS, SAFE_ALLOWED_EXTENSIONS)

    def test_blocked_extensions_rejected_even_if_configured(self) -> None:
        blocked = {
            '.rar', '.7z', '.tar', '.gz', '.exe', '.bat', '.cmd',
            '.js', '.vbs', '.scr', '.msi', '.docm', '.xlsm', '.pptm',
        }
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS | blocked, max_attachment_mb=15)):
            for extension in blocked:
                with self.subTest(extension=extension):
                    self.assertFalse(_is_allowed(_attachment(f'blocked{extension}')))

    def test_trial_allows_safe_document_and_image_extensions(self) -> None:
        with (
            patch('bewaarhet.processor.ensure_customer', return_value=({
                'status': 'trial',
                'document_count': 0,
                'storage_used_mb': 0,
            }, False)),
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.settings', SimpleNamespace(
                customer_onboarding_enabled=True,
                trial_allowed_extensions=TRIAL_ALLOWED_EXTENSIONS,
                max_trial_file_size_mb=15,
                max_attachment_mb=15,
                max_trial_documents=10,
                max_trial_storage_mb=100,
            )),
        ):
            for extension in sorted(TRIAL_ALLOWED_EXTENSIONS):
                with self.subTest(extension=extension):
                    self.assertTrue(_prepare_customer_for_storage('user@example.com', extension=extension, size_bytes=100))

        send_html.assert_not_called()

    def test_trial_unsupported_filetype_uses_specific_subject(self) -> None:
        with (
            patch('bewaarhet.processor.ensure_customer', return_value=({
                'status': 'trial',
                'document_count': 0,
                'storage_used_mb': 0,
            }, False)),
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.settings', SimpleNamespace(
                customer_onboarding_enabled=True,
                trial_allowed_extensions={'.pdf'},
                max_trial_file_size_mb=15,
                max_attachment_mb=15,
                max_trial_documents=10,
                max_trial_storage_mb=100,
            )),
        ):
            self.assertFalse(_prepare_customer_for_storage('user@example.com', extension='.docx', size_bytes=100))

        send_html.assert_called_once()
        self.assertEqual(send_html.call_args.args[1], 'Bestandstype niet ondersteund')
        self.assertIn('PDF, DOC, DOCX', send_html.call_args.args[2])

    def test_zip_with_safe_contents_allowed(self) -> None:
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS, max_attachment_mb=15)):
            validation = _validate_attachment(_attachment('archive.zip', content=_zip_bytes({
                'document.txt': b'hello',
                'folder/note.csv': b'a,b\n1,2\n',
            })))

        self.assertTrue(validation.ok)

    def test_zip_with_forbidden_contents_rejected(self) -> None:
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS, max_attachment_mb=15)):
            validation = _validate_attachment(_attachment('archive.zip', content=_zip_bytes({
                'document.txt': b'hello',
                'run.exe': b'MZunsafe',
            })))

        self.assertFalse(validation.ok)
        self.assertEqual(validation.reason, 'zip contains unsupported file type')
        self.assertEqual(validation.extension, '.exe')

    def test_zip_with_unknown_contents_rejected(self) -> None:
        with patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS, max_attachment_mb=15)):
            validation = _validate_attachment(_attachment('archive.zip', content=_zip_bytes({
                'document.unknown': b'hello',
            })))

        self.assertFalse(validation.ok)
        self.assertEqual(validation.reason, 'zip contains unsupported file type')
        self.assertEqual(validation.extension, '.unknown')

    def test_zip_unsupported_member_uses_specific_subject(self) -> None:
        att = _attachment('archive.zip', content=_zip_bytes({'run.exe': b'MZunsafe'}))
        mail = _mail(att)

        with (
            patch('bewaarhet.processor._ensure_customer_verified_for_storage', return_value=True),
            patch('bewaarhet.processor._prepare_customer_for_storage', return_value=True),
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.settings', SimpleNamespace(allowed_extensions=ALLOWED_EXTENSIONS, max_attachment_mb=15)),
        ):
            process_upload_mail(mail)

        send_html.assert_called_once()
        self.assertEqual(send_html.call_args.args[1], 'Bestandstype niet ondersteund')
        self.assertIn('ZIP-bestanden', send_html.call_args.args[2])

    def test_generic_zip_gets_semantic_filename_from_context(self) -> None:
        att = _attachment('1234.zip', content=_zip_bytes())
        mail = _mail(att)

        with (
            patch('bewaarhet.processor.ocr_space') as ocr_space,
            patch('bewaarhet.processor._resolve_filename_collision', side_effect=lambda _customer, _category, filename: filename),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.add_document') as add_document,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
            patch('bewaarhet.processor.settings', SimpleNamespace(
                allowed_extensions=ALLOWED_EXTENSIONS,
                max_attachment_mb=15,
                dropbox_base_path='/Bewaar het/Klanten',
            )),
        ):
            process_upload_mail(mail)

        ocr_space.assert_not_called()
        send_html.assert_called_once()
        self.assertEqual(send_html.call_args.args[1], 'Je document is veilig opgeslagen')
        self.assertIn('1234.zip', send_html.call_args.args[2])
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
