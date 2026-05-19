from __future__ import annotations

import unittest
import zipfile
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest.mock import patch

from bewaarhet.mail_client import Attachment, IncomingMail
from bewaarhet.processor import _sanitize_attachment_filename, process_upload_mail


ALLOWED_EXTENSIONS = {
    '.pdf',
    '.doc',
    '.docx',
    '.odt',
    '.xls',
    '.xlsx',
    '.ods',
    '.txt',
    '.csv',
    '.rtf',
    '.jpg',
    '.jpeg',
    '.png',
    '.gif',
    '.bmp',
    '.tiff',
    '.zip',
    '.rar',
    '.7z',
    '.tar',
    '.gz',
}


def _attachment(filename: str, content: bytes, *, size: int | None = None) -> Attachment:
    return Attachment(
        filename=filename,
        content=content,
        content_type='application/octet-stream',
        size=len(content) if size is None else size,
    )


def _mail(att: Attachment) -> IncomingMail:
    return IncomingMail(
        uid='1',
        from_email='user@example.com',
        subject='Factuur test',
        body_text='Bijgevoegd.',
        date_raw='Sun, 17 May 2026 10:00:00 +0200',
        attachments=[att],
    )


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _odf_bytes(mimetype: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('mimetype', mimetype, compress_type=zipfile.ZIP_STORED)
        archive.writestr('content.xml', b'<document>safe</document>')
        archive.writestr('META-INF/manifest.xml', b'<manifest />')
    return buffer.getvalue()


class UploadSafetyTests(unittest.TestCase):
    def _settings(self) -> SimpleNamespace:
        return SimpleNamespace(
            allowed_extensions=ALLOWED_EXTENSIONS,
            max_attachment_mb=15,
            dropbox_base_path='/Bewaar het/Klanten',
        )

    def test_valid_pdf_accepted(self) -> None:
        att = _attachment('factuur.pdf', b'%PDF-1.4\n% safe pdf')

        with (
            patch('bewaarhet.processor.settings', self._settings()),
            patch('bewaarhet.processor.ocr_space', return_value='Factuur test') as ocr_space,
            patch('bewaarhet.processor._resolve_filename_collision', side_effect=lambda _customer, _category, filename: filename),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.add_document') as add_document,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        ocr_space.assert_called_once()
        upload_file.assert_called_once()
        add_document.assert_called_once()
        send_html.assert_not_called()

    def test_valid_odt_accepted(self) -> None:
        att = _attachment('document.odt', _odf_bytes('application/vnd.oasis.opendocument.text'))

        with (
            patch('bewaarhet.processor.settings', self._settings()),
            patch('bewaarhet.processor.ocr_space', return_value='ODT tekst') as ocr_space,
            patch('bewaarhet.processor._resolve_filename_collision', side_effect=lambda _customer, _category, filename: filename),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.add_document') as add_document,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        ocr_space.assert_called_once()
        upload_file.assert_called_once()
        add_document.assert_called_once()
        send_html.assert_not_called()

    def test_valid_ods_accepted(self) -> None:
        att = _attachment('sheet.ods', _odf_bytes('application/vnd.oasis.opendocument.spreadsheet'))

        with (
            patch('bewaarhet.processor.settings', self._settings()),
            patch('bewaarhet.processor.ocr_space', return_value='ODS tekst') as ocr_space,
            patch('bewaarhet.processor._resolve_filename_collision', side_effect=lambda _customer, _category, filename: filename),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.add_document') as add_document,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        ocr_space.assert_called_once()
        upload_file.assert_called_once()
        add_document.assert_called_once()
        send_html.assert_not_called()

    def test_valid_rtf_accepted(self) -> None:
        att = _attachment('note.rtf', b'{\\rtf1 safe text}')

        with (
            patch('bewaarhet.processor.settings', self._settings()),
            patch('bewaarhet.processor.ocr_space', return_value='RTF tekst') as ocr_space,
            patch('bewaarhet.processor._resolve_filename_collision', side_effect=lambda _customer, _category, filename: filename),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.add_document') as add_document,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        ocr_space.assert_called_once()
        upload_file.assert_called_once()
        add_document.assert_called_once()
        send_html.assert_not_called()

    def test_exe_rejected(self) -> None:
        att = _attachment('setup.exe', b'MZ executable')

        with (
            patch('bewaarhet.processor.settings', self._settings()),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        upload_file.assert_not_called()
        send_html.assert_called_once()

    def test_fake_pdf_with_exe_content_rejected(self) -> None:
        att = _attachment('factuur.pdf', b'MZ executable')
        output = StringIO()

        with (
            patch('bewaarhet.processor.settings', self._settings()),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
            redirect_stdout(output),
        ):
            process_upload_mail(_mail(att))

        upload_file.assert_not_called()
        send_html.assert_called_once()
        self.assertIn('reason=extension/content mismatch', output.getvalue())
        self.assertIn('detected_type=executable', output.getvalue())

    def test_odt_with_exe_content_rejected(self) -> None:
        att = _attachment('document.odt', b'MZ executable')

        with (
            patch('bewaarhet.processor.settings', self._settings()),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        upload_file.assert_not_called()
        send_html.assert_called_once()

    def test_docm_rejected(self) -> None:
        settings = self._settings()
        settings.allowed_extensions = settings.allowed_extensions | {'.docm'}
        att = _attachment('macro.docm', _zip_bytes({'word/document.xml': b'<xml />'}))

        with (
            patch('bewaarhet.processor.settings', settings),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        upload_file.assert_not_called()
        send_html.assert_called_once()

    def test_xlsm_rejected(self) -> None:
        settings = self._settings()
        settings.allowed_extensions = settings.allowed_extensions | {'.xlsm'}
        att = _attachment('macro.xlsm', _zip_bytes({'xl/workbook.xml': b'<xml />'}))

        with (
            patch('bewaarhet.processor.settings', settings),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        upload_file.assert_not_called()
        send_html.assert_called_once()

    def test_unknown_extension_rejected(self) -> None:
        settings = self._settings()
        settings.allowed_extensions = settings.allowed_extensions | {'.madeup'}
        att = _attachment('document.madeup', b'safe')

        with (
            patch('bewaarhet.processor.settings', settings),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        upload_file.assert_not_called()
        send_html.assert_called_once()

    def test_zip_with_traversal_path_rejected(self) -> None:
        att = _attachment('archive.zip', _zip_bytes({'../evil.txt': b'hello'}))

        with (
            patch('bewaarhet.processor.settings', self._settings()),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        upload_file.assert_not_called()
        send_html.assert_called_once()

    def test_zip_with_too_many_files_rejected(self) -> None:
        files = {f'file_{index}.txt': b'hello' for index in range(21)}
        att = _attachment('archive.zip', _zip_bytes(files))

        with (
            patch('bewaarhet.processor.settings', self._settings()),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        upload_file.assert_not_called()
        send_html.assert_called_once()

    def test_zip_with_nested_zip_rejected(self) -> None:
        inner_zip = _zip_bytes({'inner.txt': b'hello'})
        att = _attachment('archive.zip', _zip_bytes({'nested.zip': inner_zip}))

        with (
            patch('bewaarhet.processor.settings', self._settings()),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        upload_file.assert_not_called()
        send_html.assert_called_once()

    def test_zip_with_dangerous_content_rejected(self) -> None:
        att = _attachment('archive.zip', _zip_bytes({'run.exe': b'MZ executable'}))

        with (
            patch('bewaarhet.processor.settings', self._settings()),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        upload_file.assert_not_called()
        send_html.assert_called_once()

    def test_oversized_file_rejected(self) -> None:
        att = _attachment('factuur.pdf', b'%PDF-1.4\nsmall content', size=15 * 1024 * 1024 + 1)

        with (
            patch('bewaarhet.processor.settings', self._settings()),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        upload_file.assert_not_called()
        send_html.assert_called_once()

    def test_filename_sanitization_and_unsafe_filename_rejection(self) -> None:
        self.assertEqual(_sanitize_attachment_filename('..\\evil.pdf'), 'evil.pdf')
        att = _attachment('..\\evil.pdf', b'%PDF-1.4\nsafe')

        with (
            patch('bewaarhet.processor.settings', self._settings()),
            patch('bewaarhet.processor.upload_file') as upload_file,
            patch('bewaarhet.processor.send_html') as send_html,
            patch('bewaarhet.processor.apply_rate_limit_or_reply', return_value=True),
        ):
            process_upload_mail(_mail(att))

        upload_file.assert_not_called()
        send_html.assert_called_once()


if __name__ == '__main__':
    unittest.main()
