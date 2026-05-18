from __future__ import annotations

import email
import imaplib
import smtplib
import sys
import time
import traceback
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.utils import parseaddr
from typing import Iterable

from bs4 import BeautifulSoup

from .config import settings


@dataclass
class Attachment:
    filename: str
    content: bytes
    content_type: str
    size: int


@dataclass
class IncomingMail:
    uid: str
    from_email: str
    subject: str
    body_text: str
    date_raw: str
    attachments: list[Attachment]
    to_email: str = ''

    @property
    def has_attachments(self) -> bool:
        return bool(self.attachments)


def _decode(value: str | None) -> str:
    if not value:
        return ''
    return str(make_header(decode_header(value)))


def _plain_from_html(html: str) -> str:
    return BeautifulSoup(html, 'html.parser').get_text(' ', strip=True)


def _body_text(msg: Message) -> str:
    texts: list[str] = []
    htmls: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disposition = str(part.get('Content-Disposition', '')).lower()
            if 'attachment' in disposition:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or 'utf-8'
            decoded = payload.decode(charset, errors='replace')
            if ctype == 'text/plain':
                texts.append(decoded)
            elif ctype == 'text/html':
                htmls.append(_plain_from_html(decoded))
    else:
        payload = msg.get_payload(decode=True) or b''
        charset = msg.get_content_charset() or 'utf-8'
        decoded = payload.decode(charset, errors='replace')
        if msg.get_content_type() == 'text/html':
            htmls.append(_plain_from_html(decoded))
        else:
            texts.append(decoded)
    return '\n'.join(texts or htmls).strip()


def _attachments(msg: Message) -> list[Attachment]:
    items: list[Attachment] = []
    for part in msg.walk():
        disposition = str(part.get('Content-Disposition', '')).lower()
        filename = _decode(part.get_filename())
        if not filename and 'attachment' not in disposition:
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        items.append(Attachment(filename=filename or 'bijlage', content=payload, content_type=part.get_content_type(), size=len(payload)))
    return items


def _recipient_text(msg: Message) -> str:
    values: list[str] = []
    for header in ('To', 'Cc', 'Delivered-To', 'X-Original-To', 'Envelope-To'):
        for value in msg.get_all(header, []):
            values.append(_decode(value))
    return ' '.join(values).lower()


def fetch_unseen() -> list[IncomingMail]:
    with imaplib.IMAP4_SSL(settings.zoho_imap_host, settings.zoho_imap_port) as imap:
        imap.login(settings.zoho_email, settings.zoho_app_password)
        imap.select('INBOX')
        status, data = imap.uid('search', None, 'UNSEEN')
        if status != 'OK':
            return []
        mails: list[IncomingMail] = []
        for uid_b in data[0].split():
            uid = uid_b.decode()
            status, raw_data = imap.uid('fetch', uid, '(RFC822)')
            if status != 'OK' or not raw_data or not raw_data[0]:
                continue
            raw = raw_data[0][1]
            msg = email.message_from_bytes(raw)
            _, from_email = parseaddr(_decode(msg.get('From')))
            mails.append(IncomingMail(
                uid=uid,
                from_email=from_email.lower(),
                subject=_decode(msg.get('Subject')),
                body_text=_body_text(msg),
                date_raw=_decode(msg.get('Date')),
                attachments=_attachments(msg),
                to_email=_recipient_text(msg),
            ))
        return mails

def mark_as_seen(uid: str) -> None:
    with imaplib.IMAP4_SSL(settings.zoho_imap_host, settings.zoho_imap_port) as imap:
        imap.login(settings.zoho_email, settings.zoho_app_password)
        imap.select('INBOX')
        imap.uid('store', uid, '+FLAGS', '(\\Seen)')    



def send_html(to: str, subject: str, html: str) -> None:
    msg = EmailMessage()
    msg['From'] = f'Bewaarhet <{settings.zoho_email}>'
    msg['To'] = to
    msg['Subject'] = subject
    msg['Reply-To'] = settings.zoho_email
    msg.set_content(BeautifulSoup(html, 'html.parser').get_text('\n'))
    msg.add_alternative(html, subtype='html')

    attachment_count = len(list(msg.iter_attachments()))
    smtp_started = time.perf_counter()
    print(f"SMTP send started | recipient={to} | attachment_count={attachment_count}")
    try:
        with smtplib.SMTP(settings.zoho_smtp_host, settings.zoho_smtp_port) as smtp:
            smtp.starttls()
            smtp.login(settings.zoho_email, settings.zoho_app_password)
            response = smtp.send_message(msg)
            print(f"SMTP server response | recipient={to} | refused_recipients={response}")
        smtp_duration = time.perf_counter() - smtp_started
        print(f"SMTP send completed successfully | recipient={to} | duration={smtp_duration:.3f}s")
    except Exception:
        smtp_duration = time.perf_counter() - smtp_started
        print(f"SMTP send failed | recipient={to} | attachment_count={attachment_count} | duration={smtp_duration:.3f}s")
        traceback.print_exc(file=sys.stdout)
        raise
if __name__ == "__main__":
    print("Zoho IMAP test gestart...")
    mails = fetch_unseen()
    print(f"Verbinding gelukt. Aantal ongelezen mails gevonden: {len(mails)}")

    for mail in mails[:5]:
        print("-" * 40)
        print(f"Van: {mail.from_email}")
        print(f"Onderwerp: {mail.subject}")
        print(f"Bijlagen: {len(mail.attachments)}")
