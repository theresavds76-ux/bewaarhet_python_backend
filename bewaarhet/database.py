from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .config import settings

SCHEMA = '''
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_email TEXT NOT NULL,
    safe_customer_folder TEXT NOT NULL,
    category TEXT NOT NULL,
    filename TEXT NOT NULL,
    date_received TEXT NOT NULL,
    dropbox_path TEXT NOT NULL,
    original_filename TEXT DEFAULT '',
    document_date TEXT DEFAULT '',
    domain TEXT DEFAULT '',
    ocr_preview TEXT DEFAULT '',
    ocr_text TEXT DEFAULT '',
    year TEXT DEFAULT '',
    month TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_email, filename, date_received, dropbox_path)
);

CREATE INDEX IF NOT EXISTS idx_documents_customer ON documents(customer_email);
CREATE INDEX IF NOT EXISTS idx_documents_safe_customer ON documents(safe_customer_folder);
CREATE INDEX IF NOT EXISTS idx_documents_search ON documents(customer_email, category, filename, year, month);
'''


def connect() -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_documents_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {row['name'] for row in conn.execute("PRAGMA table_info(documents)")}
    if 'original_filename' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN original_filename TEXT DEFAULT ''")
    if 'document_date' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN document_date TEXT DEFAULT ''")
    if 'domain' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN domain TEXT DEFAULT ''")


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _ensure_documents_columns(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_domain_search ON documents(customer_email, domain)")


def add_document(record: dict) -> None:
    with connect() as conn:
        _ensure_documents_columns(conn)
        conn.execute(
            '''
            INSERT OR REPLACE INTO documents
            (customer_email, safe_customer_folder, category, filename, date_received,
             dropbox_path, original_filename, document_date, domain, ocr_preview, ocr_text, year, month)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                record['customer_email'], record['safe_customer_folder'], record['category'],
                record['filename'], record['date_received'], record['dropbox_path'],
                record.get('original_filename', ''), record.get('document_date', ''),
                record.get('domain', ''),
                record.get('ocr_preview', ''), record.get('ocr_text', ''),
                record.get('year', ''), record.get('month', ''),
            ),
        )


SYNONYM_GROUPS = [
    {'belasting', 'btw', 'aangifte', 'belastingdienst', 'aanslag', 'loonheffing', 'omzetbelasting'},
    {'wonen', 'woning', 'huis', 'huur', 'woningbouw', 'woningcorporatie', 'huurcontract'},
    {'zorg', 'tandarts', 'huisarts', 'apotheek', 'ziekenhuis', 'fysiotherapeut', 'zorgverzekering'},
    {'verzekeringen', 'verzekering', 'verzekeraar', 'polis', 'premie', 'schadeclaim'},
    {'auto', 'garage', 'apk', 'kenteken', 'voertuig', 'autoverzekering'},
    {'kinderen', 'school', 'kinderopvang', 'bso', 'ouderbijdrage', 'lesgeld'},
    {'werk', 'loonstrook', 'salarisstrook', 'werkgever', 'jaaropgave', 'uwv'},
    {'garantie', 'aankoopbewijs', 'serienummer', 'retour', 'reparatie'},
    {'abonnementen', 'abonnement', 'telecom', 'streaming', 'lidmaatschap'},
    {'financien', 'bank', 'bankafschrift', 'rekeningafschrift', 'lening', 'hypotheek', 'creditcard'},
    {'schoonheidssalon', 'nagels', 'manicure', 'beauty', 'salon'},
]


def _expand_search_terms(terms: list[str]) -> list[str]:
    expanded: set[str] = set()
    for term in terms:
        expanded.add(term)
        for group in SYNONYM_GROUPS:
            if term in group:
                expanded.update(group)
    return sorted(expanded)


def search_documents(customer_email: str, query: str, limit: int = 10) -> list[sqlite3.Row]:
    terms = [t.lower() for t in query.split() if len(t) > 1]
    if not terms:
        terms = [query.lower()]

    terms = _expand_search_terms(terms)

    search_parts = []
    params: list[str] = [customer_email.lower()]

    for term in terms:
        like = f'%{term}%'
        search_parts.append(
            '(lower(filename) LIKE ? OR lower(category) LIKE ? OR lower(domain) LIKE ? OR lower(ocr_preview) LIKE ? OR lower(ocr_text) LIKE ? OR year LIKE ? OR month LIKE ?)'
        )
        params.extend([like, like, like, like, like, like, like])

    sql = f'''
        SELECT * FROM documents
        WHERE lower(customer_email) = ?
        AND (
            {' OR '.join(search_parts)}
        )
        ORDER BY date_received DESC, id DESC
        LIMIT ?
    '''

    params.append(limit)

    with connect() as conn:
        _ensure_documents_columns(conn)
        return list(conn.execute(sql, params))
