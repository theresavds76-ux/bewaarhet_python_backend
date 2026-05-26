from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath

from .config import settings
from .mail_client import Attachment
from .utils import file_extension

logger = logging.getLogger(__name__)

SAFE_ALLOWED_EXTENSIONS = {
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
    '.heic',
    '.heif',
    '.zip',
}

BLOCKED_EXTENSIONS = {
    '.rar',
    '.7z',
    '.tar',
    '.gz',
    '.exe',
    '.js',
    '.vbs',
    '.bat',
    '.cmd',
    '.ps1',
    '.scr',
    '.msi',
    '.html',
    '.php',
    '.docm',
    '.xlsm',
    '.pptm',
}

MAX_FILENAME_CHARS = 180
MAX_ZIP_FILES = 20
MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 30 * 1024 * 1024
MAX_ZIP_MEMBER_BYTES = 15 * 1024 * 1024
HEIF_BRANDS = {
    b'heic',
    b'heix',
    b'hevc',
    b'hevx',
    b'heim',
    b'heis',
    b'hevm',
    b'hevs',
    b'heif',
    b'mif1',
    b'msf1',
}


@dataclass(frozen=True)
class AttachmentValidation:
    ok: bool
    reason: str = ''
    extension: str = ''
    detected_type: str = ''
    safe_filename: str = ''


def _sanitize_attachment_filename(filename: str) -> str:
    name = (filename or '').strip()
    name = re.sub(r'[\x00-\x1f\x7f]+', '', name)
    name = name.replace('\\', '/').split('/')[-1]
    name = name.strip(' .')
    if len(name) > MAX_FILENAME_CHARS:
        path = PurePosixPath(name)
        suffix = path.suffix
        stem_limit = max(1, MAX_FILENAME_CHARS - len(suffix))
        name = f'{path.stem[:stem_limit]}{suffix}'
    return name


def _filename_has_unsafe_metadata(filename: str) -> bool:
    raw = filename or ''
    if not raw.strip() or len(raw) > MAX_FILENAME_CHARS:
        return True
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        return True
    normalized = raw.replace('\\', '/')
    if '/' in normalized or '..' in normalized:
        return True
    if re.match(r'(?i)^[a-z]:', raw):
        return True
    return _sanitize_attachment_filename(raw) != raw.strip()


def _extension_allowed(extension: str, app_settings=None) -> bool:
    active_settings = app_settings or settings
    configured = getattr(active_settings, 'allowed_extensions', SAFE_ALLOWED_EXTENSIONS) or SAFE_ALLOWED_EXTENSIONS
    if not extension or extension in BLOCKED_EXTENSIONS:
        return False
    return extension in SAFE_ALLOWED_EXTENSIONS and extension in configured


def _is_allowed(att: Attachment, app_settings=None) -> bool:
    extension = file_extension(att.filename)
    return _extension_allowed(extension, app_settings)


def _max_file_size_mb(app_settings=None) -> float:
    active_settings = app_settings or settings
    return float(getattr(active_settings, 'max_file_size_mb', getattr(active_settings, 'max_attachment_mb', 15)))


def _too_large(att: Attachment, app_settings=None) -> bool:
    return att.size > _max_file_size_mb(app_settings) * 1024 * 1024


def _is_zip(att: Attachment) -> bool:
    return file_extension(att.filename) == '.zip'


def _detect_zip_based_type(content: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            mimetype = ''
            if 'mimetype' in names:
                try:
                    mimetype = archive.read('mimetype', pwd=None).decode('ascii', errors='ignore').strip()
                except Exception:
                    mimetype = ''
    except zipfile.BadZipFile:
        return 'invalid_zip'
    if '[Content_Types].xml' in names and any(name.startswith('word/') for name in names):
        return 'docx'
    if '[Content_Types].xml' in names and any(name.startswith('xl/') for name in names):
        return 'xlsx'
    if mimetype == 'application/vnd.oasis.opendocument.text' or (
        'content.xml' in names and 'META-INF/manifest.xml' in names and any(name.endswith('.odt') for name in names)
    ):
        return 'odt'
    if mimetype == 'application/vnd.oasis.opendocument.spreadsheet' or (
        'content.xml' in names and 'META-INF/manifest.xml' in names and any(name.endswith('.ods') for name in names)
    ):
        return 'ods'
    return 'zip'


def _detect_content_type(content: bytes, extension: str = '') -> str:
    sample = content[:4096]
    if sample.startswith(b'MZ'):
        return 'executable'
    if sample.startswith(b'%PDF-'):
        return 'pdf'
    if sample.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        return 'ole'
    if sample.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if sample.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if sample.startswith((b'GIF87a', b'GIF89a')):
        return 'gif'
    if sample.startswith(b'BM'):
        return 'bmp'
    if sample.startswith((b'II*\x00', b'MM\x00*')):
        return 'tiff'
    if len(sample) >= 12 and sample[4:8] == b'ftyp':
        brands = [sample[8:12]]
        brands.extend(sample[index:index + 4] for index in range(16, min(len(sample), 64), 4))
        if any(brand in HEIF_BRANDS for brand in brands):
            return 'heif'
    if sample.startswith((b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08')):
        return _detect_zip_based_type(content)
    if sample.lstrip().startswith(b'{\\rtf'):
        return 'rtf'
    if extension in {'.txt', '.csv'}:
        if b'\x00' in sample:
            return 'binary'
        try:
            sample.decode('utf-8')
        except UnicodeDecodeError:
            try:
                sample.decode('latin-1')
            except UnicodeDecodeError:
                return 'binary'
        return 'text'
    return 'unknown'


def _content_type_matches_extension(extension: str, detected_type: str) -> bool:
    expected = {
        '.pdf': {'pdf'},
        '.doc': {'ole'},
        '.docx': {'docx'},
        '.odt': {'odt'},
        '.xls': {'ole'},
        '.xlsx': {'xlsx'},
        '.ods': {'ods'},
        '.txt': {'text'},
        '.csv': {'text'},
        '.rtf': {'rtf'},
        '.jpg': {'jpg'},
        '.jpeg': {'jpg'},
        '.png': {'png'},
        '.gif': {'gif'},
        '.bmp': {'bmp'},
        '.tiff': {'tiff'},
        '.heic': {'heif'},
        '.heif': {'heif'},
        '.zip': {'zip'},
    }
    return detected_type in expected.get(extension, set())


def _zip_member_has_unsafe_path(name: str) -> bool:
    normalized = (name or '').replace('\\', '/')
    if not normalized or normalized.startswith('/'):
        return True
    if re.match(r'(?i)^[a-z]:', normalized):
        return True
    parts = [part for part in normalized.split('/') if part]
    if any(part in {'.', '..'} for part in parts):
        return True
    return any(_filename_has_unsafe_metadata(part) for part in parts if part)


def _validate_zip_contents(content: bytes, app_settings=None) -> AttachmentValidation:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            files = [info for info in archive.infolist() if not info.is_dir()]
            if not files:
                logger.debug('zip contains no files')
                return AttachmentValidation(False, 'zip contains no files', '.zip', 'zip')
            if len(files) > MAX_ZIP_FILES:
                logger.debug('zip has too many files: %s', len(files))
                return AttachmentValidation(False, 'zip has too many files', '.zip', 'zip')

            total_uncompressed = 0
            for info in files:
                if _zip_member_has_unsafe_path(info.filename):
                    logger.debug('zip contains unsafe path: %s', info.filename)
                    return AttachmentValidation(False, 'zip contains unsafe path', '.zip', 'zip')
                if info.file_size <= 0:
                    logger.debug('zip contains empty file: %s', info.filename)
                    return AttachmentValidation(False, 'zip contains empty file', '.zip', 'zip')
                if info.file_size > MAX_ZIP_MEMBER_BYTES:
                    logger.debug('zip member too large: %s', info.filename)
                    return AttachmentValidation(False, 'zip member too large', '.zip', 'zip')
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES:
                    logger.debug('zip total uncompressed size too large: %s', total_uncompressed)
                    return AttachmentValidation(False, 'zip total uncompressed size too large', '.zip', 'zip')

                extension = file_extension(info.filename)
                if extension in {'.zip', '.rar', '.7z', '.tar', '.gz'}:
                    logger.debug('zip contains nested archive: %s', info.filename)
                    return AttachmentValidation(False, 'zip contains nested archive', extension, 'zip')
                if not _extension_allowed(extension, app_settings):
                    logger.debug('zip contains unsupported file type: %s', extension)
                    return AttachmentValidation(False, 'zip contains unsupported file type', extension, 'zip')

                with archive.open(info) as member:
                    detected = _detect_content_type(member.read(min(info.file_size, 4096)), extension)
                if extension in {'.docx', '.xlsx', '.odt', '.ods'}:
                    with archive.open(info) as member:
                        detected = _detect_content_type(member.read(), extension)
                if not _content_type_matches_extension(extension, detected):
                    logger.debug('zip member extension/content mismatch: %s detected %s', extension, detected)
                    return AttachmentValidation(False, 'zip member extension/content mismatch', extension, detected)
    except zipfile.BadZipFile:
        logger.debug('invalid zip archive')
        return AttachmentValidation(False, 'invalid zip archive', '.zip', 'invalid_zip')

    return AttachmentValidation(True, extension='.zip', detected_type='zip')


def _validate_attachment(att: Attachment, app_settings=None) -> AttachmentValidation:
    metadata_validation = _validate_attachment_metadata(att, app_settings)
    if not metadata_validation.ok:
        return metadata_validation
    return _validate_attachment_content(att, metadata_validation, app_settings)


def _validate_attachment_metadata(att: Attachment, app_settings=None) -> AttachmentValidation:
    safe_filename = _sanitize_attachment_filename(att.filename)
    extension = file_extension(safe_filename)
    size = len(att.content or b'')

    if _filename_has_unsafe_metadata(att.filename):
        logger.debug('unsafe filename: %s', att.filename)
        return AttachmentValidation(False, 'unsafe filename', extension, 'unknown', safe_filename)
    if not extension or not _extension_allowed(extension, app_settings):
        logger.debug('unsupported file type: %s', extension)
        return AttachmentValidation(False, 'unsupported file type', extension or 'none', 'unknown', safe_filename)
    if size <= 0 or att.size <= 0:
        logger.debug('empty file: %s', att.filename)
        return AttachmentValidation(False, 'empty file', extension, 'unknown', safe_filename)
    if _too_large(att, app_settings) or size > _max_file_size_mb(app_settings) * 1024 * 1024:
        logger.debug('file too large: %s (%s bytes)', att.filename, size)
        return AttachmentValidation(False, 'file too large', extension, 'unknown', safe_filename)
    return AttachmentValidation(True, extension=extension, detected_type='unchecked', safe_filename=safe_filename)


def _validate_attachment_content(att: Attachment, metadata_validation: AttachmentValidation, app_settings=None) -> AttachmentValidation:
    extension = metadata_validation.extension
    safe_filename = metadata_validation.safe_filename
    detected_type = _detect_content_type(att.content, extension)
    if not _content_type_matches_extension(extension, detected_type):
        logger.debug('extension/content mismatch: %s detected %s', extension, detected_type)
        return AttachmentValidation(False, 'extension/content mismatch', extension, detected_type, safe_filename)
    if extension == '.zip':
        zip_validation = _validate_zip_contents(att.content, app_settings)
        if not zip_validation.ok:
            return AttachmentValidation(False, zip_validation.reason, zip_validation.extension, zip_validation.detected_type, safe_filename)

    return AttachmentValidation(True, extension=extension, detected_type=detected_type, safe_filename=safe_filename)
