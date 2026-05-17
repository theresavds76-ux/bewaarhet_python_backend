from __future__ import annotations

import re

from rapidfuzz import fuzz

from .config import settings
from .database import mark_missing_file, search_documents
from .dropbox_client import is_not_found_error, temporary_link
from .mail_client import send_html
from .utils import html_escape


WEAK_QUERY_TERMS = {
    'aan', 'bij', 'de', 'dit', 'document', 'een', 'en', 'het', 'ik', 'in',
    'je', 'jouw', 'mijn', 'naar', 'of', 'op', 'te', 'van', 'voor', 'zoek',
}

QUERY_TERM_EXPANSIONS = {
    'belastingformulier': [
        'belasting', 'kwijtschelding', 'kwijtscheldingsformulier',
        'gemeentebelastingen',
    ],
    'huurcontract': ['huur', 'contract', 'wonen', 'woning'],
    'rekening': ['rekening'],
    'polis': ['polis', 'verzekering'],
}


def _normalize(text: object) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', str(text or '').lower()).strip()


def _tokens(text: object) -> set[str]:
    return set(_normalize(text).split())


def _row_value(row, key: str) -> str:
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return ''
    return str(value or '')


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    for term in _normalize(query).split():
        candidates = [term, *QUERY_TERM_EXPANSIONS.get(term, [])]
        for candidate in candidates:
            if len(candidate) <= 1 or candidate in WEAK_QUERY_TERMS or candidate in seen:
                continue
            terms.append(candidate)
            seen.add(candidate)

    return terms or [_normalize(query)]


def _exact_matches(terms: list[str], text: str) -> set[str]:
    text_tokens = _tokens(text)
    normalized_text = _normalize(text)
    return {
        term for term in terms
        if term in text_tokens or f' {term} ' in f' {normalized_text} '
    }


def _fuzzy_boost(terms: list[str], text: str, weight: int) -> int:
    normalized_text = _normalize(text)
    if not normalized_text:
        return 0

    boost = 0
    for term in terms:
        if term in _exact_matches([term], normalized_text):
            continue
        ratio = fuzz.partial_ratio(term, normalized_text)
        if ratio >= 88:
            boost += weight
        elif ratio >= 75:
            boost += max(1, weight // 2)
    return boost


def _score(row, query: str) -> int:
    terms = _query_terms(query)
    fields = {
        'filename': _row_value(row, 'filename'),
        'supplier': _row_value(row, 'supplier'),
        'purpose_title': ' '.join([
            _row_value(row, 'purpose'),
            _row_value(row, 'title'),
            _row_value(row, 'original_filename'),
        ]),
        'category_domain': ' '.join([
            _row_value(row, 'category'),
            _row_value(row, 'domain'),
        ]),
        'ocr_preview': _row_value(row, 'ocr_preview'),
    }

    filename_matches = _exact_matches(terms, fields['filename'])
    supplier_matches = _exact_matches(terms, fields['supplier'])
    purpose_title_matches = _exact_matches(terms, fields['purpose_title'])
    category_domain_matches = _exact_matches(terms, fields['category_domain'])
    ocr_preview_matches = _exact_matches(terms, fields['ocr_preview'])

    matched_terms = (
        filename_matches
        | supplier_matches
        | purpose_title_matches
        | category_domain_matches
        | ocr_preview_matches
    )

    score = 0
    score += len(filename_matches) * 25
    score += len(supplier_matches) * 25
    score += len(purpose_title_matches) * 20
    score += len(category_domain_matches) * 15
    score += len(ocr_preview_matches) * 10

    if len(filename_matches) >= 2:
        score += 35
    if len(matched_terms) >= 2:
        score += 10

    score += _fuzzy_boost(terms, fields['filename'], 8)
    score += _fuzzy_boost(terms, fields['supplier'], 8)
    score += _fuzzy_boost(terms, fields['purpose_title'], 6)
    score += _fuzzy_boost(terms, fields['category_domain'], 5)
    score += _fuzzy_boost(terms, fields['ocr_preview'], 3)

    return min(100, int(score))


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
        except Exception as exc:
            print(f"Dropbox path niet gevonden: {path}")
            if is_not_found_error(exc):
                mark_missing_file(row['id'])
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
