from __future__ import annotations

import re
from html import escape
from pathlib import Path


def safe_customer_folder(email_address: str) -> str:
    return email_address.strip().lower().replace('@', '_at_').replace('+', '_plus_')


def file_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def is_probable_search_email(subject: str, body: str, has_attachments: bool) -> bool:
    if has_attachments:
        return False
    text = f'{subject}\n{body}'.strip().lower()
    search_words = ('zoek', 'vind', 'stuur', 'document', 'bon', 'factuur', 'contract', 'belasting', 'aangifte')
    return any(word in text for word in search_words)


def extract_search_text(subject: str, body: str) -> str:
    text = f'{subject}\n{body}'
    text = re.sub(r'(?i)^(re:|fw:|fwd:)\s*', '', text.strip())
    text = re.sub(r'(?i)\b(zoek|vind|stuur|graag|document|documenten|mijn|de|het|een|naar|voor)\b', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:200]


def html_escape(text: str) -> str:
    return escape(text or '', quote=True)

def clean_filename(text: str) -> str:
    text = text.lower()

    replacements = {
        ' ': '_',
        '/': '-',
        '\\': '-',
        ':': '-',
        ';': '',
        ',': '',
        '__': '_',
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    allowed = 'abcdefghijklmnopqrstuvwxyz0123456789_-.' 
    text = ''.join(c for c in text if c in allowed)

    while '__' in text:
        text = text.replace('__', '_')

    return text.strip('_')

def generate_filename(
    category: str,
    original_filename: str,
    ocr_text: str,
    date_received: str,
    subject: str = '',
) -> str:

    extension = file_extension(original_filename)

    text = f'{subject}\n{ocr_text}'.lower()
    document_date = extract_document_date(text, date_received)

    document_types = {
        'facturen': 'factuur',
        'bonnen': 'bon',
        'contracten': 'contract',
        'belasting': 'belasting',
        'overig': 'document',
    }

    document_type = document_types.get(category, 'document')

    supplier_keywords = {
        'belastingdienst': ['belastingdienst', 'betalingskenmerk', 'btw', 'aangifte', 'aanslag'],
        'kpn': ['kpn'],
        'ziggo': ['ziggo'],
        'odido': ['odido'],
        'ikea': ['ikea'],
        'kruidvat': ['kruidvat'],
        'jumbo': ['jumbo'],
        'albert_heijn': ['albert heijn', ' ah '],
        'hema': ['hema'],
        'woningbouw': ['woningbouw', 'woningcorporatie', 'huur'],
        'schoonheidssalon': ['schoonheidssalon', 'nagels', 'manicure', 'beauty'],
    }

    subject_words = clean_filename(subject).replace('.', '').split('_')
    subject_hint = '_'.join([w for w in subject_words if len(w) > 2][:3])

    supplier = ''

    for supplier_name, keywords in supplier_keywords.items():
        if any(keyword in text for keyword in keywords):
            supplier = supplier_name
            break

    if not supplier:
        supplier = subject_hint or 'onbekend'

    filename = f'{document_date}_{document_type}_{supplier}{extension}'

    return clean_filename(filename)

def extract_document_date(text: str, fallback_date: str) -> str:
    import re

    patterns = [
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{2}-\d{2}-\d{4})',
        r'(\d{2}/\d{2}/\d{4})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            date = match.group(1)

            if '/' in date:
                day, month, year = date.split('/')
                return f'{year}-{month}-{day}'

            if len(date.split('-')[0]) == 2:
                day, month, year = date.split('-')
                return f'{year}-{month}-{day}'

            return date

    return fallback_date