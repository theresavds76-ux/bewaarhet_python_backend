from __future__ import annotations

from rapidfuzz import fuzz

from .config import settings
from .database import search_documents
from .dropbox_client import temporary_link
from .mail_client import send_html
from .utils import html_escape


def _score(row, query: str) -> int:
    haystack = ' '.join([
        row['filename'] or '', row['category'] or '', row['domain'] or '',
        row['ocr_preview'] or '', row['year'] or '', row['month'] or ''
    ]).lower()
    return int(fuzz.partial_ratio(query.lower(), haystack))


def send_search_results(customer_email: str, query: str) -> None:
    rows = search_documents(customer_email, query, settings.search_result_limit)
    ranked = sorted(rows, key=lambda r: _score(r, query), reverse=True)

    if not ranked:
        send_html(customer_email, 'Geen passend document gevonden', f'''
            Hoi,<br><br>
            Ik kon geen passend document vinden bij je zoekopdracht:<br><br>
            <b>{html_escape(query)}</b><br><br>
            Ik heb gezocht in bestandsnamen, categorieën, jaartallen en OCR-tekst binnen jouw map.<br><br>
            Probeer eventueel iets specifieker, bijvoorbeeld:<br>
            - kruidvat bon<br>
            - ikea bon 2025<br>
            - btw aangifte 2025<br>
            - factuur kpn<br>
            - contract ziggo<br><br>
            Groet,<br>
            Bewaarhet
        ''')
        return

    blocks = []
    for row in ranked:
        path = row['dropbox_path']
        try:
            link = temporary_link(path)
        except Exception:
            print(f"Dropbox path niet gevonden: {path}")
            continue

        score = _score(row, query)
        blocks.append(f'''
            <div style="padding:12px; border:1px solid #dddddd; border-radius:8px; background:#f7f7f7; margin-bottom:10px;">
                <b>{html_escape(row['filename'])}</b><br>
                Categorie: {html_escape(row['category'])}<br>
                Domein: {html_escape(row['domain'] or 'overig')}<br>
                Datum: {html_escape(row['date_received'])}<br>
                Relevantie: <b>{score}%</b><br>
                <a href="{html_escape(link)}">Download document</a>
            </div>
        ''')

    if not blocks:
        send_html(customer_email, 'Bestand niet meer gevonden', f'''
            Hoi,<br><br>
            Ik vond wel gegevens die lijken te passen, maar het bestand zelf kon niet meer in Dropbox worden gevonden.<br><br>
            Zoekopdracht:<br>
            <b>{html_escape(query)}</b><br><br>
            Groet,<br>
            Bewaarhet
        ''')
        return

    send_html(customer_email, 'Document(en) gevonden', f'''
        Hoi,<br><br>
        Ik heb deze documenten gevonden bij je zoekopdracht:<br><br>
        <b>{html_escape(query)}</b><br><br>
        {''.join(blocks)}
        De downloadlinks verlopen automatisch.<br><br>
        Groet,<br>
        Bewaarhet
    ''')
