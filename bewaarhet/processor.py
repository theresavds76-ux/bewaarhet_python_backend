from __future__ import annotations

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
    is_probable_search_email,
    safe_customer_folder,
    detect_supplier,
    detect_purpose,
    detect_domain,
)


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


def _is_allowed(att: Attachment) -> bool:
    return file_extension(att.filename) in settings.allowed_extensions


def _too_large(att: Attachment) -> bool:
    return att.size > settings.max_attachment_mb * 1024 * 1024


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

        ocr_text = ocr_space(att.content, att.filename)
        category = classify_document(
            ocr_text,
            att.filename,
            mail.subject,
            mail.body_text[:500],
        )

        supplier = detect_supplier(ocr_text, mail.subject, att.filename, mail.from_email)
        purpose = detect_purpose(ocr_text, mail.subject)
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

    if is_probable_search_email(mail.subject, mail.body_text, mail.has_attachments):
        query = extract_search_text(mail.subject, mail.body_text)
        print(f"Zoekmail herkend. Zoekterm: {query}")
        send_search_results(mail.from_email, query)
        print("Zoekresultaten verstuurd.")
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
