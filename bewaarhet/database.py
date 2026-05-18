from __future__ import annotations

import sqlite3
import re
from pathlib import Path
from typing import Iterable

from .config import settings
from .utils import canonical_customer_identity

SCHEMA = '''
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_identity TEXT NOT NULL DEFAULT '',
    customer_email TEXT NOT NULL,
    safe_customer_folder TEXT NOT NULL,
    category TEXT NOT NULL,
    filename TEXT NOT NULL,
    date_received TEXT NOT NULL,
    dropbox_path TEXT NOT NULL,
    original_filename TEXT DEFAULT '',
    document_date TEXT DEFAULT '',
    domain TEXT DEFAULT '',
    supplier TEXT DEFAULT '',
    purpose TEXT DEFAULT '',
    title TEXT DEFAULT '',
    ocr_preview TEXT DEFAULT '',
    ocr_text TEXT DEFAULT '',
    year TEXT DEFAULT '',
    month TEXT DEFAULT '',
    missing_file INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_email, filename, date_received, dropbox_path)
);

CREATE INDEX IF NOT EXISTS idx_documents_customer ON documents(customer_email);
CREATE INDEX IF NOT EXISTS idx_documents_customer_identity ON documents(customer_identity);
CREATE INDEX IF NOT EXISTS idx_documents_safe_customer ON documents(safe_customer_folder);
CREATE INDEX IF NOT EXISTS idx_documents_search ON documents(customer_email, category, filename, year, month);

CREATE TABLE IF NOT EXISTS rate_limit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_events ON rate_limit_events(sender, action, created_at);

CREATE TABLE IF NOT EXISTS rate_limit_cooldowns (
    sender TEXT NOT NULL,
    action TEXT NOT NULL,
    cooldown_start INTEGER NOT NULL,
    cooldown_until INTEGER NOT NULL,
    PRIMARY KEY(sender, action)
);
'''


def connect() -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_documents_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {row['name'] for row in conn.execute("PRAGMA table_info(documents)")}
    if 'customer_identity' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN customer_identity TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE documents SET customer_identity = lower(customer_email) WHERE customer_identity = ''")
    if 'original_filename' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN original_filename TEXT DEFAULT ''")
    if 'document_date' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN document_date TEXT DEFAULT ''")
    if 'domain' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN domain TEXT DEFAULT ''")
    if 'supplier' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN supplier TEXT DEFAULT ''")
    if 'purpose' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN purpose TEXT DEFAULT ''")
    if 'title' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN title TEXT DEFAULT ''")
    if 'missing_file' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN missing_file INTEGER NOT NULL DEFAULT 0")


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _ensure_documents_columns(conn)
        ensure_rate_limit_tables(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_domain_search ON documents(customer_email, domain)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_customer_identity ON documents(customer_identity)")


def ensure_rate_limit_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS rate_limit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            action TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        '''
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rate_limit_events ON rate_limit_events(sender, action, created_at)")
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS rate_limit_cooldowns (
            sender TEXT NOT NULL,
            action TEXT NOT NULL,
            cooldown_start INTEGER NOT NULL,
            cooldown_until INTEGER NOT NULL,
            PRIMARY KEY(sender, action)
        )
        '''
    )


def add_document(record: dict) -> None:
    customer_identity = canonical_customer_identity(record.get('customer_identity') or record['customer_email'])
    with connect() as conn:
        _ensure_documents_columns(conn)
        conn.execute(
            '''
            INSERT OR REPLACE INTO documents
            (customer_identity, customer_email, safe_customer_folder, category, filename, date_received,
             dropbox_path, original_filename, document_date, domain, supplier, purpose, title,
             ocr_preview, ocr_text, year, month)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                customer_identity,
                canonical_customer_identity(record['customer_email']), record['safe_customer_folder'], record['category'],
                record['filename'], record['date_received'], record['dropbox_path'],
                record.get('original_filename', ''), record.get('document_date', ''),
                record.get('domain', ''),
                record.get('supplier', ''), record.get('purpose', ''), record.get('title', ''),
                record.get('ocr_preview', ''), record.get('ocr_text', ''),
                record.get('year', ''), record.get('month', ''),
            ),
        )


def mark_missing_file(document_id: int) -> None:
    with connect() as conn:
        _ensure_documents_columns(conn)
        conn.execute(
            'UPDATE documents SET missing_file = 1 WHERE id = ?',
            (document_id,),
        )


def all_documents() -> list[sqlite3.Row]:
    with connect() as conn:
        _ensure_documents_columns(conn)
        return list(conn.execute('SELECT * FROM documents ORDER BY id'))


SYNONYM_GROUPS = [
    {
        'belasting', 'belastingformulier', 'formulier', 'kwijtschelding',
        'kwijtscheldingsformulier', 'gemeentebelastingen', 'btw', 'aangifte',
        'belastingdienst', 'aanslag', 'loonheffing', 'omzetbelasting',
    },
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
    {'wachtwoord', 'password', 'login', 'gebruikersnaam', 'account', 'ww'},
    {'code', 'pincode', 'sleutel'},
]

SEARCH_FILLER_WORDS = {
    'aan', 'bij', 'de', 'dit', 'document', 'een', 'en', 'het', 'ik', 'in',
    'je', 'jouw', 'me', 'mij', 'mijn', 'naar', 'of', 'op', 'te', 'van',
    'voor', 'zoek', 'vind', 'stuur', 'graag',
}

SEARCH_ALIASES = {
    'mn': 'mijn',
    "m'n": 'mijn',
    'ww': 'wachtwoord',
}


def _query_terms(query: str) -> list[str]:
    normalized = re.sub(r'[^a-z0-9]+', ' ', (query or '').lower())
    terms = [
        SEARCH_ALIASES.get(term, term)
        for term in normalized.split()
        if len(term) > 1
    ]
    filtered = [term for term in terms if term not in SEARCH_FILLER_WORDS]
    return filtered or [term for term in terms if term] or [normalized.strip()]


def _expand_search_terms(terms: list[str]) -> list[str]:
    expanded: set[str] = set()
    for term in terms:
        expanded.add(term)
        for group in SYNONYM_GROUPS:
            if term in group:
                expanded.update(group)
    return sorted(expanded)


def search_documents(customer_email: str, query: str, limit: int = 10) -> list[sqlite3.Row]:
    terms = _expand_search_terms(_query_terms(query))
    customer_identity = canonical_customer_identity(customer_email)

    search_parts = []
    params: list[str] = [customer_identity]

    for term in terms:
        like = f'%{term}%'
        search_parts.append(
            '(lower(filename) LIKE ? OR lower(category) LIKE ? OR lower(domain) LIKE ? OR lower(supplier) LIKE ? OR lower(purpose) LIKE ? OR lower(title) LIKE ? OR lower(ocr_preview) LIKE ? OR lower(ocr_text) LIKE ? OR lower(dropbox_path) LIKE ? OR year LIKE ? OR month LIKE ?)'
        )
        params.extend([like, like, like, like, like, like, like, like, like, like, like])

    sql = f'''
        SELECT * FROM documents
        WHERE lower(COALESCE(NULLIF(customer_identity, ''), customer_email)) = ?
        AND COALESCE(missing_file, 0) = 0
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
