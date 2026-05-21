from __future__ import annotations

import re
import textwrap
import zipfile
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import PurePosixPath
from email.utils import parsedate_to_datetime

from .classifier import classify_document
from .config import settings
from .customer_onboarding import activation_link
from .database import add_document, connect, ensure_customer
from .dropbox_client import upload_file
from .mail_client import Attachment, IncomingMail, mark_as_seen, send_html
from .ocr import ocr_space
from .rate_limiter import apply_rate_limit_or_reply
from .search_reply import send_search_results
from .utils import (
    canonical_customer_identity,
    extract_search_text,
    file_extension,
    generate_filename,
    html_escape,
    is_document_email_without_attachment,
    is_probable_search_email,
    safe_customer_folder,
    sanitize_for_log,
    strip_email_signature,
    is_note_like_content,
    detect_supplier,
    detect_purpose,
    detect_domain,
)


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

SUPPORTED_FILE_TYPES_TEXT = 'PDF, DOC, DOCX, ODT, XLS, XLSX, ODS, TXT, CSV, RTF, JPG, JPEG, PNG, GIF, BMP, TIFF en ZIP'

MAX_FILENAME_CHARS = 180
MAX_ZIP_FILES = 20
MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 30 * 1024 * 1024
MAX_ZIP_MEMBER_BYTES = 15 * 1024 * 1024


@dataclass(frozen=True)
class AttachmentValidation:
    ok: bool
    reason: str = ''
    extension: str = ''
    detected_type: str = ''
    safe_filename: str = ''


def _recipient_contains(mail: IncomingMail, address: str) -> bool:
    return address.lower() in (getattr(mail, 'to_email', '') or '').lower()


def _is_self_trigger_mail(mail: IncomingMail) -> bool:
    sender = canonical_customer_identity(mail.from_email)
    service_addresses = {
        canonical_customer_identity(settings.zoho_email),
        'service@bewaarhet.nl',
        'bewaren@bewaarhet.nl',
        'zoek@bewaarhet.nl',
    }
    service_addresses = {address for address in service_addresses if address}
    return sender in service_addresses


def _search_query_from_mail(mail: IncomingMail) -> str:
    return f'{mail.subject}\n{mail.body_text}'.strip()[:200]


def _log_route(route: str, reason: str) -> None:
    print(f"Route gekozen: {route} | Reden: {reason}")


def _has_service_search_intent(mail: IncomingMail) -> bool:
    import re

    text = f'{mail.subject}\n{mail.body_text}'.lower()
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return False

    possessive = r"(?:mijn|mn|m'n|me|mij)"
    patterns = [
        rf'\bik\s+zoek\s+(?:{possessive}\s+)?\S+',
        rf'\bzoek\s+(?:{possessive}\s+)?\S+',
        rf'\b(?:kun|kan)\s+je\s+(?:{possessive}\s+)?[^.?!]{{0,80}}\bvinden\b',
        rf'\bkunt\s+u\s+(?:{possessive}\s+)?[^.?!]{{0,80}}\bvinden\b',
        rf'\bheb\s+je\s+(?:{possessive}\s+)[^.?!]{{1,80}}',
        rf'\bstuur\s+(?:{possessive}\s+)?[^.?!]{{1,80}}',
        rf'\bwaar\s+is\s+(?:{possessive}\s+)?[^.?!]{{1,80}}',
        rf'\bik\s+kan\s+(?:{possessive}\s+)?[^.?!]{{1,80}}\bniet\s+vinden\b',
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _received_parts(mail: IncomingMail) -> tuple[str, str, str]:
    try:
        dt = parsedate_to_datetime(mail.date_raw)
    except Exception:
        dt = datetime.now()
    return dt.strftime('%Y-%m-%d'), dt.strftime('%Y'), dt.strftime('%m')


def _dropbox_path(customer: str, category: str, filename: str) -> str:
    return f'{settings.dropbox_base_path}/{customer}/{category}/{filename}'


def _filename_exists(customer: str, category: str, filename: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            'SELECT 1 FROM documents WHERE safe_customer_folder = ? AND category = ? AND filename = ? LIMIT 1',
            (customer, category, filename),
        ).fetchone()
        return bool(row)


def _resolve_filename_collision(customer: str, category: str, filename: str) -> str:
    from pathlib import Path

    path = Path(filename)
    base = path.stem
    ext = path.suffix
    candidate = filename
    counter = 1
    while _filename_exists(customer, category, candidate):
        candidate = f'{base}_{counter}{ext}'
        counter += 1
    return candidate


def _sender_domain(sender_email: str) -> str:
    if '@' not in (sender_email or ''):
        return ''
    return sender_email.rsplit('@', 1)[1].lower()


def _log_supplier_debug(
    *,
    original_filename: str,
    mail_subject: str,
    sender_email: str,
    ocr_text: str,
    supplier: str,
    purpose: str,
    generated_filename: str,
) -> None:
    print("[supplier-debug] begin")
    print(f"[supplier-debug] original_filename: {sanitize_for_log(original_filename)}")
    print(f"[supplier-debug] mail subject: {sanitize_for_log(mail_subject)}")
    print(f"[supplier-debug] sender email/domain: {sender_email} / {_sender_domain(sender_email)}")
    print(f"[supplier-debug] sanitized OCR preview: {sanitize_for_log(ocr_text)[:100]}")
    print(f"[supplier-debug] detected supplier: {supplier}")
    print(f"[supplier-debug] detected purpose: {purpose}")
    print(f"[supplier-debug] generated filename: {sanitize_for_log(generated_filename)}")
    print("[supplier-debug] end")


def _log_semantic_debug(category: str, purpose: str, ignored_signature_chars: int = 0) -> None:
    semantic_type = 'notitie' if category == 'notities' or purpose == 'notitie' else category
    print(f"[semantic-debug] detected semantic type: {semantic_type}")
    print(f"[semantic-debug] detected purpose: {purpose or 'onbekend'}")
    print(f"[semantic-debug] ignored signature/footer length: {ignored_signature_chars}")


def _log_storage_debug(record: dict, searchable_text: str) -> None:
    print("[storage-debug] begin")
    print(f"[storage-debug] customer_email: {record.get('customer_email', '')}")
    print(f"[storage-debug] safe_customer_folder: {record.get('safe_customer_folder', '')}")
    print(f"[storage-debug] category: {record.get('category', '')}")
    print(f"[storage-debug] filename: {sanitize_for_log(record.get('filename', ''))}")
    print(f"[storage-debug] ocr_preview length: {len(record.get('ocr_preview', '') or '')}")
    print(f"[storage-debug] ocr_text length: {len(record.get('ocr_text', '') or '')}")
    print(f"[storage-debug] sanitized searchable preview: {sanitize_for_log(searchable_text)[:100]}")
    print("[storage-debug] end")


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


def _extension_allowed(extension: str) -> bool:
    configured = getattr(settings, 'allowed_extensions', SAFE_ALLOWED_EXTENSIONS) or SAFE_ALLOWED_EXTENSIONS
    if not extension or extension in BLOCKED_EXTENSIONS:
        return False
    return extension in SAFE_ALLOWED_EXTENSIONS and extension in configured


def _is_allowed(att: Attachment) -> bool:
    extension = file_extension(att.filename)
    return _extension_allowed(extension)


def _too_large(att: Attachment) -> bool:
    return att.size > _max_file_size_mb() * 1024 * 1024


def _max_file_size_mb() -> float:
    return float(getattr(settings, 'max_file_size_mb', getattr(settings, 'max_attachment_mb', 15)))


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


def _validate_zip_contents(content: bytes) -> AttachmentValidation:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            files = [info for info in archive.infolist() if not info.is_dir()]
            if len(files) > MAX_ZIP_FILES:
                return AttachmentValidation(False, 'zip has too many files', '.zip', 'zip')

            total_uncompressed = 0
            for info in files:
                if _zip_member_has_unsafe_path(info.filename):
                    return AttachmentValidation(False, 'zip contains unsafe path', '.zip', 'zip')
                if info.file_size <= 0:
                    return AttachmentValidation(False, 'zip contains empty file', '.zip', 'zip')
                if info.file_size > MAX_ZIP_MEMBER_BYTES:
                    return AttachmentValidation(False, 'zip member too large', '.zip', 'zip')
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES:
                    return AttachmentValidation(False, 'zip total uncompressed size too large', '.zip', 'zip')

                extension = file_extension(info.filename)
                if extension in {'.zip', '.rar', '.7z', '.tar', '.gz'}:
                    return AttachmentValidation(False, 'zip contains nested archive', extension, 'zip')
                if not _extension_allowed(extension):
                    return AttachmentValidation(False, 'zip contains unsupported file type', extension, 'zip')

                with archive.open(info) as member:
                    detected = _detect_content_type(member.read(min(info.file_size, 4096)), extension)
                if extension in {'.docx', '.xlsx', '.odt', '.ods'}:
                    with archive.open(info) as member:
                        detected = _detect_content_type(member.read(), extension)
                if not _content_type_matches_extension(extension, detected):
                    return AttachmentValidation(False, 'zip member extension/content mismatch', extension, detected)
    except zipfile.BadZipFile:
        return AttachmentValidation(False, 'invalid zip archive', '.zip', 'invalid_zip')

    return AttachmentValidation(True, extension='.zip', detected_type='zip')


def _validate_attachment(att: Attachment) -> AttachmentValidation:
    metadata_validation = _validate_attachment_metadata(att)
    if not metadata_validation.ok:
        return metadata_validation
    return _validate_attachment_content(att, metadata_validation)


def _validate_attachment_metadata(att: Attachment) -> AttachmentValidation:
    safe_filename = _sanitize_attachment_filename(att.filename)
    extension = file_extension(safe_filename)
    size = len(att.content or b'')

    if _filename_has_unsafe_metadata(att.filename):
        return AttachmentValidation(False, 'unsafe filename', extension, 'unknown', safe_filename)
    if not extension or not _extension_allowed(extension):
        return AttachmentValidation(False, 'unsupported file type', extension or 'none', 'unknown', safe_filename)
    if size <= 0 or att.size <= 0:
        return AttachmentValidation(False, 'empty file', extension, 'unknown', safe_filename)
    if _too_large(att) or size > _max_file_size_mb() * 1024 * 1024:
        return AttachmentValidation(False, 'file too large', extension, 'unknown', safe_filename)
    return AttachmentValidation(True, extension=extension, detected_type='unchecked', safe_filename=safe_filename)


def _validate_attachment_content(att: Attachment, metadata_validation: AttachmentValidation) -> AttachmentValidation:
    extension = metadata_validation.extension
    safe_filename = metadata_validation.safe_filename
    detected_type = _detect_content_type(att.content, extension)
    if not _content_type_matches_extension(extension, detected_type):
        return AttachmentValidation(False, 'extension/content mismatch', extension, detected_type, safe_filename)
    if extension == '.zip':
        zip_validation = _validate_zip_contents(att.content)
        if not zip_validation.ok:
            return AttachmentValidation(False, zip_validation.reason, zip_validation.extension, zip_validation.detected_type, safe_filename)

    return AttachmentValidation(True, extension=extension, detected_type=detected_type, safe_filename=safe_filename)


def _onboarding_enabled() -> bool:
    return bool(getattr(settings, 'customer_onboarding_enabled', False))


def _legacy_welcome_email_unused(to: str) -> None:
    subject = getattr(settings, 'welcome_email_subject', 'Welkom bij Bewaarhet')
    send_html(to, subject, '''
        Hoi,<br><br>
        Welkom bij Bewaarhet 😊<br><br>
        Je eerste documenten zijn ontvangen. Je kunt documenten bewaren door ze naar Bewaarhet te mailen.
        Als je later iets zoekt, mail je gewoon wat je nodig hebt, bijvoorbeeld: "zoek mijn polis" of "zoek recept pastei".<br><br>
        Je start met een kleine trial. Daarmee kun je veilig kennismaken met Bewaarhet:
        maximaal 10 documenten en 100 MB opslag. Tijdens de trial accepteren we PDF, JPG en PNG.<br><br>
        Je documenten worden veilig opgeslagen en downloadlinks verlopen automatisch.<br><br>
        Vragen of iets werkt niet zoals verwacht? Reageer gerust op deze mail.<br><br>
        Groet,<br>
        Bewaarhet
    ''')


def _send_welcome_email(to: str) -> None:
    subject = getattr(settings, 'welcome_email_subject', 'Welkom bij Bewaarhet')
    link = html_escape(activation_link(to))
    body = f'''
        Hoi,<br><br>
        Welkom bij Bewaarhet.<br><br>
        Bewaarhet helpt je documenten bewaren via e-mail. Je mailt een document naar Bewaarhet,
        en daarna kan het automatisch worden herkend, netjes hernoemd en opgeslagen.
        Later kun je het weer opvragen via zoek@bewaarhet.nl.<br><br>
        Je start met een gratis proefomgeving. Daarmee kun je rustig testen met bijvoorbeeld
        facturen, bonnetjes, recepten, notities, contracten en handleidingen.<br><br>
        De proef ondersteunt deze bestandstypen: {SUPPORTED_FILE_TYPES_TEXT}.<br><br>
        Bevestig eerst je e-mailadres om de proef te starten:<br><br>
        <a href="{link}" style="display:inline-block;padding:12px 18px;background:#1f6feb;color:#ffffff;text-decoration:none;border-radius:6px;">Start mijn gratis proef</a><br><br>
        Of open deze link:<br>
        <a href="{link}">{link}</a><br><br>
        Groet,<br>
        Bewaarhet
    '''
    send_html(to, subject, body)


def _send_pending_verification_reminder(to: str) -> None:
    link = html_escape(activation_link(to))
    body = f'''
        Hoi,<br><br>
        Bevestig eerst je e-mailadres. Daarna kun je Bewaarhet testen met je documenten.<br><br>
        <a href="{link}" style="display:inline-block;padding:12px 18px;background:#1f6feb;color:#ffffff;text-decoration:none;border-radius:6px;">Bevestig mijn e-mailadres</a><br><br>
        Of open deze link:<br>
        <a href="{link}">{link}</a><br><br>
        Groet,<br>
        Bewaarhet
    '''
    send_html(to, 'Bevestig je e-mailadres voor Bewaarhet', body)


def _send_blocked_customer_reply(to: str) -> None:
    send_html(to, 'Bewaarhet account geblokkeerd', '''
        Hoi,<br><br>
        Dit e-mailadres kan op dit moment geen documenten verwerken via Bewaarhet.
        Neem contact op als je denkt dat dit niet klopt.<br><br>
        Groet,<br>
        Bewaarhet
    ''')


def _send_trial_limit_reply(to: str, reason: str) -> None:
    send_html(to, 'Triallimiet bereikt', f'''
        Hoi,<br><br>
        Je document is niet verwerkt, omdat de triallimiet is bereikt: {html_escape(reason)}.<br><br>
        Tijdens de trial kun je maximaal {getattr(settings, 'max_trial_documents', 10)} documenten en
        {getattr(settings, 'max_trial_storage_mb', 100)} MB bewaren. Bestandstypen die kunnen:
        {SUPPORTED_FILE_TYPES_TEXT}.<br><br>
        Reageer op deze mail als je Bewaarhet verder wilt gebruiken.<br><br>
        Groet,<br>
        Bewaarhet
    ''')


def _send_unsupported_filetype_reply(to: str, reason: str) -> None:
    send_html(to, 'Bestandstype niet ondersteund', f'''
        Hoi,<br><br>
        Je document is niet verwerkt: {html_escape(reason)}.<br><br>
        Bestandstypen die kunnen: {SUPPORTED_FILE_TYPES_TEXT}.<br>
        ZIP-bestanden kunnen alleen als alle bestanden in de ZIP ook een ondersteund bestandstype hebben.<br><br>
        Groet,<br>
        Bewaarhet
    ''')


def _try_send_trial_limit_reply(to: str, reason: str) -> None:
    try:
        _send_trial_limit_reply(to, reason)
    except Exception as exc:
        print(f"trial limit email failed | sender={sanitize_for_log(to)} | error={sanitize_for_log(exc)}")


def _try_send_unsupported_filetype_reply(to: str, reason: str) -> None:
    try:
        _send_unsupported_filetype_reply(to, reason)
    except Exception as exc:
        print(f"unsupported filetype email failed | sender={sanitize_for_log(to)} | error={sanitize_for_log(exc)}")


def _prepare_customer_for_storage(sender: str, *, extension: str, size_bytes: int) -> bool:
    if not _onboarding_enabled():
        return True

    sender_identity = canonical_customer_identity(sender)
    try:
        customer, created = ensure_customer(sender_identity)
    except Exception as exc:
        print(f"customer lookup failed | sender={sanitize_for_log(sender_identity)} | error={sanitize_for_log(exc)}")
        return False

    status = str(customer['status'] or '').lower()
    if created:
        print(f"new pending verification customer created | sender={sanitize_for_log(sender_identity)}")
        try:
            _send_welcome_email(sender_identity)
        except Exception as exc:
            print(f"welcome email failed | sender={sanitize_for_log(sender_identity)} | error={sanitize_for_log(exc)}")
        return False

    if status == 'pending_verification':
        print(f"pending verification customer rejected before processing | sender={sanitize_for_log(sender_identity)}")
        try:
            _send_pending_verification_reminder(sender_identity)
        except Exception as exc:
            print(f"verification reminder email failed | sender={sanitize_for_log(sender_identity)} | error={sanitize_for_log(exc)}")
        return False

    if status == 'blocked':
        print(f"blocked customer rejected | sender={sanitize_for_log(sender_identity)}")
        try:
            _send_blocked_customer_reply(sender_identity)
        finally:
            return False

    rate_action = 'trial_storage_mail' if status == 'trial' else 'storage'
    try:
        if not apply_rate_limit_or_reply(sender_identity, rate_action):
            print(f"rate limit exceeded before processing | sender={sanitize_for_log(sender_identity)} | action={rate_action}")
            return False
    except Exception as exc:
        print(f"rate limit check failed | sender={sanitize_for_log(sender_identity)} | action={rate_action} | error={sanitize_for_log(exc)}")
        return False

    if status != 'trial':
        return True

    trial_allowed = getattr(settings, 'trial_allowed_extensions', SAFE_ALLOWED_EXTENSIONS)
    if extension not in trial_allowed:
        print(f"trial file type rejected | sender={sanitize_for_log(sender_identity)} | extension={sanitize_for_log(extension)}")
        _try_send_unsupported_filetype_reply(sender_identity, 'dit bestandstype is niet ondersteund in de trial')
        return False

    max_file_size_mb = float(getattr(settings, 'max_trial_file_size_mb', getattr(settings, 'max_attachment_mb', 15)))
    if size_bytes > max_file_size_mb * 1024 * 1024:
        print(f"trial file too large | sender={sanitize_for_log(sender_identity)} | size={size_bytes}")
        _try_send_trial_limit_reply(sender_identity, f'dit bestand is groter dan {max_file_size_mb:g} MB')
        return False

    try:
        if not apply_rate_limit_or_reply(sender_identity, 'trial_document'):
            print(f"trial document rate limit exceeded | sender={sanitize_for_log(sender_identity)}")
            return False
    except Exception as exc:
        print(f"trial document rate limit check failed | sender={sanitize_for_log(sender_identity)} | error={sanitize_for_log(exc)}")
        return False

    current_count = int(customer['document_count'] or 0)
    current_storage = float(customer['storage_used_mb'] or 0)
    max_documents = int(getattr(settings, 'max_trial_documents', 10))
    max_storage = float(getattr(settings, 'max_trial_storage_mb', 100))
    next_storage = current_storage + (max(0, size_bytes) / (1024 * 1024))

    if current_count >= max_documents:
        print(f"trial document limit reached | sender={sanitize_for_log(sender_identity)} | count={current_count}")
        _try_send_trial_limit_reply(sender_identity, 'het maximale aantal trial-documenten is bereikt')
        return False
    if next_storage > max_storage:
        print(f"trial storage limit reached | sender={sanitize_for_log(sender_identity)} | storage_mb={current_storage:.3f}")
        _try_send_trial_limit_reply(sender_identity, 'de maximale trial-opslag is bereikt')
        return False
    return True


def _ensure_customer_verified_for_storage(sender: str) -> bool:
    if not _onboarding_enabled():
        return True

    sender_identity = canonical_customer_identity(sender)
    try:
        customer, created = ensure_customer(sender_identity)
    except Exception as exc:
        print(f"customer lookup failed | sender={sanitize_for_log(sender_identity)} | error={sanitize_for_log(exc)}")
        return False

    status = str(customer['status'] or '').lower()
    if created:
        print(f"new pending verification customer created | sender={sanitize_for_log(sender_identity)}")
        try:
            _send_welcome_email(sender_identity)
        except Exception as exc:
            print(f"welcome email failed | sender={sanitize_for_log(sender_identity)} | error={sanitize_for_log(exc)}")
        return False
    if status == 'pending_verification':
        print(f"pending verification customer rejected before processing | sender={sanitize_for_log(sender_identity)}")
        try:
            _send_pending_verification_reminder(sender_identity)
        except Exception as exc:
            print(f"verification reminder email failed | sender={sanitize_for_log(sender_identity)} | error={sanitize_for_log(exc)}")
        return False
    if status == 'blocked':
        print(f"blocked customer rejected | sender={sanitize_for_log(sender_identity)}")
        try:
            _send_blocked_customer_reply(sender_identity)
        finally:
            return False
    return True


def _log_attachment_rejected(att: Attachment, validation: AttachmentValidation) -> None:
    print(
        "Attachment rejected"
        f" | reason={sanitize_for_log(validation.reason)}"
        f" | extension={sanitize_for_log(validation.extension)}"
        f" | detected_type={sanitize_for_log(validation.detected_type)}"
        f" | size={att.size}"
    )


def _send_attachment_rejected_reply(to: str, validation: AttachmentValidation) -> None:
    send_html(to, 'Bestand niet opgeslagen', f'''
        Hoi,<br><br>
        Ik kon een bijlage niet veilig opslaan: {html_escape(validation.reason)}.<br><br>
        Ondersteunde bestandstypen zijn: {SUPPORTED_FILE_TYPES_TEXT}.<br>
        De maximale bestandsgrootte is {_max_file_size_mb():g} MB.<br><br>
        Groet,<br>
        Bewaarhet
    ''')


def _is_unsupported_filetype_rejection(validation: AttachmentValidation) -> bool:
    return validation.reason in {
        'unsupported file type',
        'zip contains unsupported file type',
        'zip contains nested archive',
    }


def _send_rejected_upload_reply(to: str, validation: AttachmentValidation) -> None:
    if _is_unsupported_filetype_rejection(validation):
        _send_unsupported_filetype_reply(to, validation.reason)
        return
    _send_attachment_rejected_reply(to, validation)


def _send_storage_success_reply(to: str, filenames: list[str]) -> None:
    stored = [filename for filename in filenames if filename]
    if not stored:
        return

    multiple = len(stored) > 1
    subject = 'Je documenten zijn veilig opgeslagen' if multiple else 'Je document is veilig opgeslagen'
    intro = 'Je documenten zijn veilig opgeslagen in Bewaarhet.' if multiple else 'Je document is veilig opgeslagen in Bewaarhet.'
    later = (
        'Als je ze later nodig hebt, kun je ons gewoon mailen met wat je zoekt.'
        if multiple
        else 'Als je het document later nodig hebt, kun je ons gewoon mailen met wat je zoekt.'
    )
    items = ''.join(f'<li>{html_escape(filename)}</li>' for filename in stored)
    send_html(to, subject, f'''
        Hoi,<br><br>
        {intro}<br><br>
        Opgeslagen:<br>
        <ul>{items}</ul>
        Je hoeft verder niets te doen. {later}<br><br>
        Groet,<br>
        Bewaarhet
    ''')


def _try_send_storage_success_reply(to: str, filenames: list[str]) -> None:
    try:
        _send_storage_success_reply(to, filenames)
    except Exception as exc:
        print(f"storage success email failed | sender={sanitize_for_log(to)} | error={sanitize_for_log(exc)}")


def _handle_rejected_upload_rate_limit(sender: str) -> bool:
    return apply_rate_limit_or_reply(sender, 'rejected_upload')


def _attachment_context_text(mail: IncomingMail) -> str:
    return f'{mail.subject}\n{mail.body_text}'.strip()


def _pdf_escape(text: str) -> str:
    return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _mail_body_pdf_bytes(subject: str, body_text: str) -> bytes:
    lines = [f'Onderwerp: {subject}', '', *(body_text or '').splitlines()]
    wrapped_lines: list[str] = []
    for line in lines:
        clean_line = line.replace('\t', '    ').strip()
        wrapped = textwrap.wrap(clean_line, width=92) or ['']
        wrapped_lines.extend(wrapped)

    pages = [wrapped_lines[index:index + 48] for index in range(0, len(wrapped_lines), 48)] or [[]]
    objects: list[bytes] = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    page_refs: list[str] = []

    for page in pages:
        page_number = len(page_refs)
        page_obj_id = 4 + page_number * 2
        content_obj_id = page_obj_id + 1
        page_refs.append(f'{page_obj_id} 0 R')

        commands = ['BT', '/F1 10 Tf', '50 790 Td', '14 TL']
        for line in page:
            safe_line = _pdf_escape(line.encode('latin-1', errors='replace').decode('latin-1'))
            commands.append(f'({safe_line}) Tj')
            commands.append('T*')
        commands.append('ET')
        stream = '\n'.join(commands).encode('latin-1')

        objects.append(
            f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj_id} 0 R >>'.encode('ascii')
        )
        objects.append(b'<< /Length ' + str(len(stream)).encode('ascii') + b' >>\nstream\n' + stream + b'\nendstream')

    objects[1] = f'<< /Type /Pages /Kids [{" ".join(page_refs)}] /Count {len(page_refs)} >>'.encode('ascii')

    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f'{index} 0 obj\n'.encode('ascii'))
        pdf.extend(obj)
        pdf.extend(b'\nendobj\n')
    xref_offset = len(pdf)
    pdf.extend(f'xref\n0 {len(objects) + 1}\n'.encode('ascii'))
    pdf.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010d} 00000 n \n'.encode('ascii'))
    pdf.extend(
        f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n'.encode('ascii')
    )
    return bytes(pdf)


def process_document_body_mail(mail: IncomingMail) -> None:
    customer_identity = canonical_customer_identity(mail.from_email)
    customer = safe_customer_folder(customer_identity)
    date_received, year, month = _received_parts(mail)
    original_filename = 'email_body.pdf'
    body_without_footer, ignored_signature_chars = strip_email_signature(mail.body_text)
    semantic_text = f'{mail.subject}\n{body_without_footer}'.strip()

    if not _prepare_customer_for_storage(
        mail.from_email,
        extension='.pdf',
        size_bytes=len(semantic_text.encode('utf-8', errors='ignore')),
    ):
        return

    if is_note_like_content(semantic_text, mail.subject, original_filename):
        category = 'notities'
        supplier = ''
        purpose = 'notitie'
        domain = 'overig'
    else:
        category = classify_document(semantic_text, original_filename, mail.subject, body_without_footer[:500])
        supplier = detect_supplier(semantic_text, mail.subject, original_filename, mail.from_email)
        purpose = detect_purpose(semantic_text, mail.subject, original_filename)
        domain = detect_domain(semantic_text, mail.subject, original_filename, supplier, purpose)

    new_filename, document_date = generate_filename(
        category,
        original_filename,
        semantic_text,
        date_received,
        mail.subject,
        supplier=supplier,
        purpose=purpose,
    )
    new_filename = _resolve_filename_collision(customer, category, new_filename)

    _log_supplier_debug(
        original_filename=original_filename,
        mail_subject=mail.subject,
        sender_email=mail.from_email,
        ocr_text=semantic_text,
        supplier=supplier,
        purpose=purpose,
        generated_filename=new_filename,
    )
    _log_semantic_debug(category, purpose, ignored_signature_chars)

    pdf_bytes = _mail_body_pdf_bytes(mail.subject, mail.body_text)
    path = _dropbox_path(customer, category, new_filename)
    upload_file(pdf_bytes, path)

    print(f"Documentmail opgeslagen als PDF: {sanitize_for_log(new_filename)}")
    print(f"Geupload naar Dropbox: {sanitize_for_log(path)}")

    record = {
        'customer_identity': customer_identity,
        'customer_email': customer_identity,
        'safe_customer_folder': customer,
        'category': category,
        'filename': new_filename,
        'original_filename': original_filename,
        'document_date': document_date,
        'domain': domain,
        'supplier': supplier,
        'purpose': purpose,
        'title': mail.subject,
        'date_received': date_received,
        'dropbox_path': path,
        'ocr_preview': semantic_text[:200],
        'ocr_text': semantic_text,
        'year': year,
        'month': month,
        'size_bytes': len(pdf_bytes),
    }
    _log_storage_debug(record, semantic_text)
    add_document(record)

    print("Opgeslagen in SQLite.")
    _try_send_storage_success_reply(mail.from_email, [new_filename])


def process_upload_mail(mail: IncomingMail) -> None:
    customer_identity = canonical_customer_identity(mail.from_email)
    customer = safe_customer_folder(customer_identity)
    date_received, year, month = _received_parts(mail)
    stored_filenames: list[str] = []

    if not _ensure_customer_verified_for_storage(mail.from_email):
        return

    for att in mail.attachments:
        print(f"Bijlage verwerken: {sanitize_for_log(att.filename)} ({att.size} bytes)")

        validation = _validate_attachment_metadata(att)
        if not validation.ok:
            _log_attachment_rejected(att, validation)
            if _handle_rejected_upload_rate_limit(mail.from_email):
                _send_rejected_upload_reply(mail.from_email, validation)
            continue

        if not _prepare_customer_for_storage(
            mail.from_email,
            extension=validation.extension,
            size_bytes=len(att.content or b''),
        ):
            continue

        validation = _validate_attachment_content(att, validation)
        if not validation.ok:
            _log_attachment_rejected(att, validation)
            if _handle_rejected_upload_rate_limit(mail.from_email):
                _send_rejected_upload_reply(mail.from_email, validation)
            continue

        original_filename = validation.safe_filename

        if validation.extension == '.zip':
            if not apply_rate_limit_or_reply(mail.from_email, 'zip_upload'):
                continue
            ocr_text = _attachment_context_text(mail)
            print("ZIP-archief opgeslagen zonder uitpakken of OCR.")
        else:
            ocr_text = ocr_space(att.content, original_filename)

        category = classify_document(
            ocr_text,
            original_filename,
            mail.subject,
            mail.body_text[:500],
        )

        if is_note_like_content(ocr_text, mail.subject, original_filename):
            category = 'notities'
            supplier = ''
            purpose = 'notitie'
            domain = 'overig'
        else:
            supplier = detect_supplier(ocr_text, mail.subject, original_filename, mail.from_email)
            purpose = detect_purpose(ocr_text, mail.subject, original_filename)
            domain = detect_domain(ocr_text, mail.subject, original_filename, supplier, purpose)

        new_filename, document_date = generate_filename(
            category,
            original_filename,
            ocr_text,
            date_received,
            mail.subject,
            supplier=supplier,
            purpose=purpose,
        )

        new_filename = _resolve_filename_collision(customer, category, new_filename)

        _log_supplier_debug(
            original_filename=original_filename,
            mail_subject=mail.subject,
            sender_email=mail.from_email,
            ocr_text=ocr_text,
            supplier=supplier,
            purpose=purpose,
            generated_filename=new_filename,
        )
        _log_semantic_debug(category, purpose)

        path = _dropbox_path(customer, category, new_filename)
        upload_file(att.content, path)

        print(f"Geüpload naar Dropbox: {sanitize_for_log(path)}")
        print(f"Nieuwe bestandsnaam: {sanitize_for_log(new_filename)}")

        record = {
            'customer_identity': customer_identity,
            'customer_email': customer_identity,
            'safe_customer_folder': customer,
            'category': category,
            'filename': new_filename,
            'original_filename': original_filename,
            'document_date': document_date,
            'domain': domain,
            'supplier': supplier,
            'purpose': purpose,
            'title': mail.subject,
            'date_received': date_received,
            'dropbox_path': path,
            'ocr_preview': ocr_text[:200],
            'ocr_text': ocr_text,
            'year': year,
            'month': month,
            'size_bytes': len(att.content or b''),
        }
        _log_storage_debug(record, ocr_text)
        add_document(record)

        print("Opgeslagen in SQLite.")
        stored_filenames.append(original_filename)

    _try_send_storage_success_reply(mail.from_email, stored_filenames)


def process_mail(mail: IncomingMail) -> None:
    if _is_self_trigger_mail(mail):
        print(f"Mail loop/self-trigger geblokkeerd | sender={sanitize_for_log(canonical_customer_identity(mail.from_email))}")
        return

    if _recipient_contains(mail, 'zoek@bewaarhet.nl'):
        query = _search_query_from_mail(mail)
        _log_route('search', 'ontvanger bevat zoek@bewaarhet.nl')
        print(f"Zoekmail herkend. Zoekterm: {sanitize_for_log(query)}")
        if not apply_rate_limit_or_reply(mail.from_email, 'search'):
            return
        send_search_results(mail.from_email, query)
        return

    if _recipient_contains(mail, 'bewaren@bewaarhet.nl'):
        _log_route('store', 'ontvanger bevat bewaren@bewaarhet.nl')
        if mail.has_attachments:
            process_upload_mail(mail)
        else:
            process_document_body_mail(mail)
        return

    if _recipient_contains(mail, 'service@bewaarhet.nl'):
        if _has_service_search_intent(mail):
            query = extract_search_text(mail.subject, mail.body_text)
            _log_route('search', 'service@bewaarhet.nl met zoekintentie')
            print(f"Zoekmail herkend. Zoekterm: {sanitize_for_log(query)}")
            if not apply_rate_limit_or_reply(mail.from_email, 'search'):
                return
            send_search_results(mail.from_email, query)
            return

        _log_route('store', 'service@bewaarhet.nl zonder zoekintentie')
        if mail.has_attachments:
            process_upload_mail(mail)
        else:
            process_document_body_mail(mail)
        return

    if mail.has_attachments:
        _log_route('store', 'mail heeft bijlagen')
        process_upload_mail(mail)
        return

    if is_probable_search_email(
        mail.subject,
        mail.body_text,
        mail.has_attachments,
        getattr(mail, 'to_email', ''),
    ):
        query = extract_search_text(mail.subject, mail.body_text)
        _log_route('search', 'expliciete zoekterm in onderwerp')
        print(f"Zoekmail herkend. Zoekterm: {sanitize_for_log(query)}")
        if not apply_rate_limit_or_reply(mail.from_email, 'search'):
            return
        send_search_results(mail.from_email, query)
        return

    if is_document_email_without_attachment(mail):
        _log_route('store', 'documentachtige mail zonder bijlage')
        process_document_body_mail(mail)
        return


if __name__ == "__main__":
    from .mail_client import fetch_unseen

    print("Processor test gestart...")
    mails = fetch_unseen()
    print(f"Aantal ongelezen mails gevonden: {len(mails)}")

    for mail in mails:
        print("-" * 40)
        print(f"Van: {mail.from_email}")
        print(f"Onderwerp: {sanitize_for_log(mail.subject)}")
        print(f"Bijlagen: {len(mail.attachments)}")

        process_mail(mail)

        print("Verwerkt.")
        mark_as_seen(mail.uid)
        print("Mail gemarkeerd als gelezen.")
