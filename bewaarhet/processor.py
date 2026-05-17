from __future__ import annotations

import textwrap
from datetime import datetime
from email.utils import parsedate_to_datetime

from .classifier import classify_document
from .config import settings
from .database import add_document, connect
from .dropbox_client import upload_file
from .mail_client import Attachment, IncomingMail, mark_as_seen
from .ocr import ocr_space
from .search_reply import send_search_results
from .utils import (
    extract_search_text,
    file_extension,
    generate_filename,
    is_document_email_without_attachment,
    is_probable_search_email,
    safe_customer_folder,
    detect_supplier,
    detect_purpose,
    detect_domain,
)


BLOCKED_EXTENSIONS = {
    '.mp4', '.mov', '.avi', '.mkv', '.webm',
    '.mp3', '.wav',
    '.exe', '.msi', '.bat', '.cmd', '.sh',
    '.rar', '.7z',
}


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
    print(f"[supplier-debug] original_filename: {original_filename}")
    print(f"[supplier-debug] mail subject: {mail_subject}")
    print(f"[supplier-debug] sender email/domain: {sender_email} / {_sender_domain(sender_email)}")
    print(f"[supplier-debug] eerste 800 tekens OCR: {(ocr_text or '')[:800]}")
    print(f"[supplier-debug] detected supplier: {supplier}")
    print(f"[supplier-debug] detected purpose: {purpose}")
    print(f"[supplier-debug] generated filename: {generated_filename}")
    print("[supplier-debug] end")


def _is_allowed(att: Attachment) -> bool:
    extension = file_extension(att.filename)
    return extension in settings.allowed_extensions and extension not in BLOCKED_EXTENSIONS


def _too_large(att: Attachment) -> bool:
    return att.size > settings.max_attachment_mb * 1024 * 1024


def _is_zip(att: Attachment) -> bool:
    return file_extension(att.filename) == '.zip'


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
    customer = safe_customer_folder(mail.from_email)
    date_received, year, month = _received_parts(mail)
    original_filename = 'email_body.pdf'
    document_text = f'{mail.subject}\n{mail.body_text}'.strip()

    category = classify_document(document_text, original_filename, mail.subject, mail.body_text[:500])
    supplier = detect_supplier(document_text, mail.subject, original_filename, mail.from_email)
    purpose = detect_purpose(document_text, mail.subject, original_filename)
    domain = detect_domain(document_text, mail.subject, original_filename, supplier, purpose)

    new_filename, document_date = generate_filename(
        category,
        original_filename,
        document_text,
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
        ocr_text=document_text,
        supplier=supplier,
        purpose=purpose,
        generated_filename=new_filename,
    )

    pdf_bytes = _mail_body_pdf_bytes(mail.subject, mail.body_text)
    path = _dropbox_path(customer, category, new_filename)
    upload_file(pdf_bytes, path)

    print(f"Documentmail opgeslagen als PDF: {new_filename}")
    print(f"Geupload naar Dropbox: {path}")

    add_document({
        'customer_email': mail.from_email,
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
        'ocr_preview': document_text[:200],
        'ocr_text': document_text,
        'year': year,
        'month': month,
    })

    print("Opgeslagen in SQLite.")


def process_upload_mail(mail: IncomingMail) -> None:
    customer = safe_customer_folder(mail.from_email)
    date_received, year, month = _received_parts(mail)

    for att in mail.attachments:
        print(f"Bijlage verwerken: {att.filename} ({att.size} bytes)")

        if _too_large(att):
            print("Bestand te groot, overgeslagen.")
            continue

        if not _is_allowed(att):
            print("Bestandstype niet toegestaan, overgeslagen.")
            continue

        if _is_zip(att):
            ocr_text = _attachment_context_text(mail)
            print("ZIP-archief opgeslagen zonder uitpakken of OCR.")
        else:
            ocr_text = ocr_space(att.content, att.filename)

        category = classify_document(
            ocr_text,
            att.filename,
            mail.subject,
            mail.body_text[:500],
        )

        supplier = detect_supplier(ocr_text, mail.subject, att.filename, mail.from_email)
        purpose = detect_purpose(ocr_text, mail.subject, att.filename)
        domain = detect_domain(ocr_text, mail.subject, att.filename, supplier, purpose)

        new_filename, document_date = generate_filename(
            category,
            att.filename,
            ocr_text,
            date_received,
            mail.subject,
            supplier=supplier,
            purpose=purpose,
        )

        new_filename = _resolve_filename_collision(customer, category, new_filename)

        _log_supplier_debug(
            original_filename=att.filename,
            mail_subject=mail.subject,
            sender_email=mail.from_email,
            ocr_text=ocr_text,
            supplier=supplier,
            purpose=purpose,
            generated_filename=new_filename,
        )

        path = _dropbox_path(customer, category, new_filename)
        upload_file(att.content, path)

        print(f"Geüpload naar Dropbox: {path}")
        print(f"Nieuwe bestandsnaam: {new_filename}")   

        add_document({
            'customer_email': mail.from_email,
            'safe_customer_folder': customer,
            'category': category,
            'filename': new_filename,
            'original_filename': att.filename,
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
        })

        print("Opgeslagen in SQLite.")


def process_mail(mail: IncomingMail) -> None:
    if mail.has_attachments:
        process_upload_mail(mail)
        return

    if is_probable_search_email(
        mail.subject,
        mail.body_text,
        mail.has_attachments,
        getattr(mail, 'to_email', ''),
    ):
        query = extract_search_text(mail.subject, mail.body_text)
        print(f"Zoekmail herkend. Zoekterm: {query}")
        send_search_results(mail.from_email, query)
        print("Zoekresultaten verstuurd.")
        return

    if is_document_email_without_attachment(mail):
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
        print(f"Onderwerp: {mail.subject}")
        print(f"Bijlagen: {len(mail.attachments)}")

        process_mail(mail)

        print("Verwerkt.")
        mark_as_seen(mail.uid)
        print("Mail gemarkeerd als gelezen.")
