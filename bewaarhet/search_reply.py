from __future__ import annotations

import re
import time

from rapidfuzz import fuzz

from .config import settings
from .database import mark_missing_file, search_documents
from .dropbox_client import is_not_found_error, temporary_link
from .mail_client import send_html
from .utils import canonical_customer_identity, html_escape, safe_customer_folder, sanitize_for_log


WEAK_QUERY_TERMS = {
    'aan', 'bij', 'de', 'dit', 'document', 'een', 'en', 'het', 'ik', 'in',
    'je', 'jouw', 'me', 'mij', 'mijn', 'naar', 'of', 'op', 'te', 'van', 'voor', 'zoek',
}

QUERY_TERM_EXPANSIONS = {
    'belastingformulier': [
        'belasting', 'kwijtschelding', 'kwijtscheldingsformulier',
        'gemeentebelastingen',
    ],
    'huurcontract': ['huur', 'contract', 'wonen', 'woning'],
    'rekening': ['rekening'],
    'polis': ['polis', 'verzekering'],
    'wachtwoord': ['password', 'login'],
    'password': ['wachtwoord', 'login'],
    'login': ['wachtwoord', 'gebruikersnaam', 'account'],
    'code': ['pincode'],
    'pincode': ['code'],
    'gebruikersnaam': ['login', 'account'],
    'account': ['login', 'gebruikersnaam'],
    'sleutel': ['code'],
}

MIN_SEARCH_RESULT_SCORE = 30

CREDENTIAL_QUERY_TERMS = {
    'wachtwoord',
    'password',
    'login',
    'code',
    'pincode',
    'gebruikersnaam',
    'account',
    'sleutel',
}

CREDENTIAL_LABELS = (
    'wachtwoord',
    'password',
    'login',
    'code',
    'pincode',
)

BUSINESS_SEARCH_CATEGORIES = {
    'facturen',
    'bonnen',
    'contracten',
    'belasting',
}

BUSINESS_SEARCH_PURPOSES = {
    'factuur',
    'bon',
    'contract',
    'huur',
    'rekening',
    'polis',
    'verzekering',
    'betalingsherinnering',
    'betaalinformatie',
    'betalingsregeling',
    'aangifte',
    'belastingaanslag',
    'kwijtschelding',
    'kwijtscheldingsformulier',
}

GENERIC_SEARCH_TERMS = BUSINESS_SEARCH_CATEGORIES | BUSINESS_SEARCH_PURPOSES | {
    'bon',
    'bonnen',
    'document',
    'documenten',
    'bestand',
    'bestanden',
    'rekening',
    'rekeningen',
    'belastingformulier',
    'huurcontract',
}

QUERY_ALIASES = {
    'mn': 'mijn',
    "m'n": 'mijn',
    'ww': 'wachtwoord',
}


def _normalize(text: object) -> str:
    normalized = re.sub(r'[^a-z0-9]+', ' ', str(text or '').lower()).strip()
    return ' '.join(QUERY_ALIASES.get(token, token) for token in normalized.split())


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


def _is_business_document(row) -> bool:
    category = _normalize(_row_value(row, 'category'))
    purpose = _normalize(_row_value(row, 'purpose'))
    return category in BUSINESS_SEARCH_CATEGORIES or purpose in BUSINESS_SEARCH_PURPOSES


def _looks_like_credential_footer(text: str) -> bool:
    normalized = _normalize(text)
    footer_phrases = (
        'wachtwoord vergeten',
        'password forgotten',
        'forgot password',
        'reset password',
        'account herstellen',
        'klik hier',
    )
    return any(phrase in normalized for phrase in footer_phrases)


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
        'ocr_text': _row_value(row, 'ocr_text'),
        'stored_text': ' '.join([
            _row_value(row, 'ocr_preview'),
            _row_value(row, 'ocr_text'),
        ]),
        'dropbox_path': _row_value(row, 'dropbox_path'),
    }

    filename_matches = _exact_matches(terms, fields['filename'])
    supplier_matches = _exact_matches(terms, fields['supplier'])
    purpose_title_matches = _exact_matches(terms, fields['purpose_title'])
    category_domain_matches = _exact_matches(terms, fields['category_domain'])
    ocr_preview_matches = _exact_matches(terms, fields['ocr_preview'])
    ocr_text_matches = _exact_matches(terms, fields['ocr_text'])
    stored_text_matches = ocr_preview_matches | ocr_text_matches
    dropbox_path_matches = _exact_matches(terms, fields['dropbox_path'])

    matched_terms = (
        filename_matches
        | supplier_matches
        | purpose_title_matches
        | category_domain_matches
        | stored_text_matches
        | dropbox_path_matches
    )
    base_query_terms = [
        term for term in _normalize(query).split()
        if len(term) > 1 and term not in WEAK_QUERY_TERMS
    ]
    strict_terms = {
        term for term in base_query_terms
        if len(term) > 1
        and term not in GENERIC_SEARCH_TERMS
        and not term.isdigit()
    }

    score = 0
    score += len(filename_matches) * 25
    score += len(supplier_matches) * 25
    score += len(purpose_title_matches) * 20
    score += len(category_domain_matches) * 15
    score += len(ocr_preview_matches) * 25
    score += len(ocr_text_matches) * 25
    score += len(dropbox_path_matches) * 8

    if len(filename_matches) >= 2:
        score += 35
    if len(matched_terms) >= 2:
        score += 10

    normalized_query_terms = set(terms)
    is_note = _normalize(_row_value(row, 'category')) == 'notities' or _normalize(_row_value(row, 'purpose')) == 'notitie'
    is_business_document = _is_business_document(row)
    credential_query_matches = normalized_query_terms & CREDENTIAL_QUERY_TERMS
    stored_text = fields['stored_text']
    has_credential_keyword = any(term in _tokens(stored_text) for term in CREDENTIAL_QUERY_TERMS)
    has_credential_label = bool(re.search(
        r'(?i)\b(?:' + '|'.join(re.escape(label) for label in CREDENTIAL_LABELS) + r')\b\s*[:=]',
        stored_text,
    ))

    if is_note and credential_query_matches and (stored_text_matches or has_credential_keyword):
        score += 35
    if is_note and credential_query_matches and has_credential_label:
        score += 20
    if is_note and len(stored_text_matches & credential_query_matches) >= 1:
        score += 10
    if credential_query_matches and has_credential_label and not is_note and not is_business_document:
        score += 8
    if credential_query_matches and has_credential_keyword and not is_business_document:
        score = max(score, MIN_SEARCH_RESULT_SCORE)
    if (
        credential_query_matches
        and is_business_document
        and not (filename_matches or supplier_matches or purpose_title_matches or category_domain_matches or dropbox_path_matches)
        and _looks_like_credential_footer(stored_text)
    ):
        score = min(score, MIN_SEARCH_RESULT_SCORE - 1)
    if credential_query_matches and not (stored_text_matches or filename_matches or purpose_title_matches or dropbox_path_matches):
        score = min(score, 20)
    missing_focused_strict_term = len(base_query_terms) <= 4 and strict_terms and not strict_terms.issubset(matched_terms)

    score += _fuzzy_boost(terms, fields['filename'], 8)
    score += _fuzzy_boost(terms, fields['supplier'], 8)
    score += _fuzzy_boost(terms, fields['purpose_title'], 6)
    score += _fuzzy_boost(terms, fields['category_domain'], 5)
    score += _fuzzy_boost(terms, fields['ocr_preview'], 3)
    score += _fuzzy_boost(terms, fields['ocr_text'], 3)
    score += _fuzzy_boost(terms, fields['dropbox_path'], 3)
    if missing_focused_strict_term:
        score = min(score, MIN_SEARCH_RESULT_SCORE - 1)

    return min(100, int(score))


def _contains_query_match(text: str, terms: list[str]) -> bool:
    return bool(_exact_matches(terms, text))


def _dropbox_path_contains_customer_folder(dropbox_path: str, expected_folder: str) -> bool:
    parts = [part for part in (dropbox_path or '').replace('\\', '/').split('/') if part]
    if not parts or any(part in {'.', '..'} for part in parts):
        return False
    return expected_folder in parts


def _record_owned_by_sender(row, search_sender: str) -> bool:
    customer_identity = canonical_customer_identity(search_sender)
    expected_folder = safe_customer_folder(customer_identity)

    row_identity = canonical_customer_identity(_row_value(row, 'customer_identity'))
    row_email = canonical_customer_identity(_row_value(row, 'customer_email'))
    row_folder = _row_value(row, 'safe_customer_folder')
    row_path = _row_value(row, 'dropbox_path')

    return (
        row_identity == customer_identity
        or row_email == customer_identity
        or row_folder == expected_folder
        or _dropbox_path_contains_customer_folder(row_path, expected_folder)
    )


def _download_link_notice(link_count: int) -> str:
    notice = 'Downloadlinks zijn tijdelijk beveiligd en verlopen automatisch na enkele uren.'
    if link_count > 1:
        notice += ' Als je meerdere documenten opent, kunnen links los van elkaar verlopen.'
    return notice


def _log_search_debug(customer_email: str, query: str, rows: list) -> None:
    terms = _query_terms(query)
    cleaned_query = ' '.join(terms)
    ranked = sorted(
        ((_score(row, query), row) for row in rows),
        key=lambda item: item[0],
        reverse=True,
    )

    print("[search-debug] begin")
    print(f"[search-debug] sender email: {customer_email}")
    print(f"[search-debug] safe_customer_folder: {safe_customer_folder(customer_email)}")
    print(f"[search-debug] cleaned query: {sanitize_for_log(cleaned_query)}")
    print(f"[search-debug] candidate records loaded from SQLite: {len(rows)}")

    for index, (score, row) in enumerate(ranked[:5], start=1):
        ocr_preview = _row_value(row, 'ocr_preview')
        ocr_text = _row_value(row, 'ocr_text')
        rejected_reason = ''
        if score < MIN_SEARCH_RESULT_SCORE:
            rejected_reason = f'score {score} below threshold {MIN_SEARCH_RESULT_SCORE}'
        print(f"[search-debug] candidate {index}")
        print(f"[search-debug] filename: {sanitize_for_log(_row_value(row, 'filename'))}")
        print(f"[search-debug] category: {_row_value(row, 'category')}")
        print(f"[search-debug] purpose: {_row_value(row, 'purpose')}")
        print(f"[search-debug] ocr_preview contains query? {'yes' if _contains_query_match(ocr_preview, terms) else 'no'}")
        print(f"[search-debug] ocr_text contains query? {'yes' if _contains_query_match(ocr_text, terms) else 'no'}")
        print(f"[search-debug] score: {score}")
        if rejected_reason:
            print(f"[search-debug] reason rejected: {rejected_reason}")
    print("[search-debug] end")


def send_search_results(customer_email: str, query: str) -> None:
    customer_identity = canonical_customer_identity(customer_email)
    rows = search_documents(customer_identity, query, settings.search_result_limit)
    _log_search_debug(customer_identity, query, rows)
    ranked = sorted(
        ((_score(row, query), row) for row in rows),
        key=lambda item: item[0],
        reverse=True,
    )
    relevant = []
    for score, row in ranked:
        if score < MIN_SEARCH_RESULT_SCORE:
            continue
        if _record_owned_by_sender(row, customer_identity):
            relevant.append((score, row))
            continue
        print(
            "ownership check failed"
            f" | recipient={customer_identity}"
            f" | document_id={sanitize_for_log(_row_value(row, 'id'))}"
            f" | filename={sanitize_for_log(_row_value(row, 'filename'))}"
        )

    print(
        "Search reply generation started"
        f" | recipient={customer_identity} | relevant_count={len(relevant)}"
    )
    print(
        "Preparing search reply attachments/links"
        f" | recipient={customer_identity} | link_candidates={len(relevant)} | attachment_count=0"
    )
    attachment_started = time.perf_counter()
    attachment_count = 0
    attachment_duration = time.perf_counter() - attachment_started
    print(
        "Attachment preparation duration"
        f" | recipient={customer_identity} | attachment_count={attachment_count}"
        f" | duration={attachment_duration:.3f}s"
    )

    if not relevant:
        print(
            "Dropbox link generation duration"
            f" | recipient={customer_identity} | generated_links=0 | duration=0.000s"
        )
        send_html(customer_identity, 'Geen passend document gevonden', f'''
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
    link_started = time.perf_counter()
    try:
        for score, row in relevant:
            path = row['dropbox_path']
            try:
                link = temporary_link(path)
            except Exception as exc:
                print(f"Dropbox path niet gevonden: {sanitize_for_log(path)}")
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
    finally:
        link_duration = time.perf_counter() - link_started
        print(
            "Dropbox link generation duration"
            f" | recipient={customer_identity} | generated_links={len(blocks)}"
            f" | duration={link_duration:.3f}s"
        )

    if not blocks:
        send_html(customer_identity, 'Bestand niet meer gevonden', f'''
            Hoi,<br><br>
            Ik vond wel gegevens die lijken te passen, maar het bestand zelf kon niet meer in Dropbox worden gevonden.<br><br>
            Zoekopdracht:<br>
            <b>{html_escape(query)}</b><br><br>
            Groet,<br>
            Bewaarhet
        ''')
        return

    send_html(customer_identity, 'Document(en) gevonden', f'''
        Hoi,<br><br>
        Ik heb deze documenten gevonden bij je zoekopdracht:<br><br>
        <b>{html_escape(query)}</b><br><br>
        {''.join(blocks)}
        {html_escape(_download_link_notice(len(blocks)))}<br><br>
        Groet,<br>
        Bewaarhet
    ''')
