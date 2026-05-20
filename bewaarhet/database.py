from __future__ import annotations

import sqlite3
import re
from contextlib import closing

from .backup import create_backup, validate_database
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

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT DEFAULT NULL,
    status TEXT NOT NULL DEFAULT 'pending_verification' CHECK(status IN ('pending_verification', 'trial', 'active', 'blocked')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    document_count INTEGER NOT NULL DEFAULT 0,
    storage_used_mb REAL NOT NULL DEFAULT 0,
    last_activity_at TEXT DEFAULT NULL,
    trial_started_at TEXT DEFAULT NULL,
    notes TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status);
'''


def connect() -> sqlite3.Connection:
    if hasattr(settings, 'ensure_directories'):
        settings.ensure_directories()
    else:
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn


DOCUMENT_COLUMNS = {
    'customer_identity',
    'original_filename',
    'document_date',
    'domain',
    'supplier',
    'purpose',
    'title',
    'ocr_preview',
    'ocr_text',
    'year',
    'month',
    'missing_file',
}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row['name']
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _schema_update_needed(conn: sqlite3.Connection) -> bool:
    tables = _table_names(conn)
    if not tables:
        return False
    if 'documents' not in tables:
        return True
    if not {'rate_limit_events', 'rate_limit_cooldowns', 'customers'}.issubset(tables):
        return True
    customer_definition = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'customers'"
    ).fetchone()
    if customer_definition and 'pending_verification' not in (customer_definition['sql'] or ''):
        return True
    existing_columns = {row['name'] for row in conn.execute("PRAGMA table_info(documents)")}
    return not DOCUMENT_COLUMNS.issubset(existing_columns)


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
    if 'ocr_preview' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN ocr_preview TEXT DEFAULT ''")
    if 'ocr_text' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN ocr_text TEXT DEFAULT ''")
    if 'year' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN year TEXT DEFAULT ''")
    if 'month' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN month TEXT DEFAULT ''")
    if 'missing_file' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN missing_file INTEGER NOT NULL DEFAULT 0")


def init_db() -> None:
    if hasattr(settings, 'ensure_directories'):
        settings.ensure_directories()
    else:
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.database_path.exists() and settings.database_path.stat().st_size > 0:
        with closing(connect()) as conn:
            needs_schema_update = _schema_update_needed(conn)
        if needs_schema_update:
            create_backup(
                database_path=settings.database_path,
                backup_dir=getattr(settings, 'backup_dir', settings.database_path.parent / 'backups'),
                keep_latest=getattr(settings, 'backup_keep_latest', 14),
                reason='pre-migration',
                require_tables=False,
            )

    with closing(connect()) as conn:
        if 'documents' in _table_names(conn):
            _ensure_documents_columns(conn)
            conn.commit()
        conn.executescript(SCHEMA)
        _ensure_documents_columns(conn)
        ensure_rate_limit_tables(conn)
        ensure_customer_table(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_domain_search ON documents(customer_email, domain)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_customer_identity ON documents(customer_identity)")
        conn.commit()


def check_integrity() -> tuple[bool, str]:
    return validate_database(settings.database_path, require_tables=False)


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


def ensure_customer_table(conn: sqlite3.Connection) -> None:
    if 'customers' in _table_names(conn):
        definition = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'customers'"
        ).fetchone()
        if definition and 'pending_verification' not in (definition['sql'] or ''):
            conn.execute('ALTER TABLE customers RENAME TO customers_legacy')
            conn.execute(
                '''
                CREATE TABLE customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT DEFAULT NULL,
                    status TEXT NOT NULL DEFAULT 'pending_verification' CHECK(status IN ('pending_verification', 'trial', 'active', 'blocked')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    document_count INTEGER NOT NULL DEFAULT 0,
                    storage_used_mb REAL NOT NULL DEFAULT 0,
                    last_activity_at TEXT DEFAULT NULL,
                    trial_started_at TEXT DEFAULT NULL,
                    notes TEXT DEFAULT NULL
                )
                '''
            )
            conn.execute(
                '''
                INSERT INTO customers
                (id, email, name, status, created_at, updated_at, document_count, storage_used_mb, last_activity_at, trial_started_at, notes)
                SELECT id, email, name, status, created_at, updated_at, document_count, storage_used_mb, last_activity_at, trial_started_at, notes
                FROM customers_legacy
                '''
            )
            conn.execute('DROP TABLE customers_legacy')
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            name TEXT DEFAULT NULL,
            status TEXT NOT NULL DEFAULT 'pending_verification' CHECK(status IN ('pending_verification', 'trial', 'active', 'blocked')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            document_count INTEGER NOT NULL DEFAULT 0,
            storage_used_mb REAL NOT NULL DEFAULT 0,
            last_activity_at TEXT DEFAULT NULL,
            trial_started_at TEXT DEFAULT NULL,
            notes TEXT DEFAULT NULL
        )
        '''
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status)")


def get_customer(email: str) -> sqlite3.Row | None:
    customer_email = canonical_customer_identity(email)
    with closing(connect()) as conn:
        ensure_customer_table(conn)
        return conn.execute('SELECT * FROM customers WHERE email = ?', (customer_email,)).fetchone()


def ensure_customer(email: str, *, name: str | None = None) -> tuple[sqlite3.Row, bool]:
    customer_email = canonical_customer_identity(email)
    if not customer_email:
        raise ValueError('customer email is required')
    with closing(connect()) as conn:
        ensure_customer_table(conn)
        existing = conn.execute('SELECT * FROM customers WHERE email = ?', (customer_email,)).fetchone()
        if existing:
            return existing, False
        conn.execute(
            '''
            INSERT INTO customers
            (email, name, status, trial_started_at, last_activity_at)
            VALUES (?, ?, 'pending_verification', NULL, CURRENT_TIMESTAMP)
            ''',
            (customer_email, name),
        )
        conn.commit()
        created = conn.execute('SELECT * FROM customers WHERE email = ?', (customer_email,)).fetchone()
        if created is None:
            raise RuntimeError('customer creation failed')
        return created, True


def update_customer_status(email: str, status: str, *, name: str | None = None, notes: str | None = None) -> sqlite3.Row:
    if status not in {'pending_verification', 'trial', 'active', 'blocked'}:
        raise ValueError(f'unsupported customer status: {status}')
    customer_email = canonical_customer_identity(email)
    with closing(connect()) as conn:
        ensure_customer_table(conn)
        conn.execute(
            '''
            INSERT INTO customers (email, name, status, trial_started_at, last_activity_at)
            VALUES (?, ?, ?, CASE WHEN ? = 'trial' THEN CURRENT_TIMESTAMP ELSE NULL END, CURRENT_TIMESTAMP)
            ON CONFLICT(email) DO UPDATE SET
                status = excluded.status,
                name = COALESCE(excluded.name, customers.name),
                notes = COALESCE(?, customers.notes),
                updated_at = CURRENT_TIMESTAMP,
                last_activity_at = CURRENT_TIMESTAMP,
                trial_started_at = CASE
                    WHEN excluded.status = 'trial' AND customers.trial_started_at IS NULL THEN CURRENT_TIMESTAMP
                    WHEN excluded.status = 'pending_verification' THEN NULL
                    ELSE customers.trial_started_at
                END
            ''',
            (customer_email, name, status, status, notes),
        )
        conn.commit()
        row = conn.execute('SELECT * FROM customers WHERE email = ?', (customer_email,)).fetchone()
        if row is None:
            raise RuntimeError('customer status update failed')
        return row


def list_customers(*, status: str | None = None, limit: int = 100) -> list[sqlite3.Row]:
    with closing(connect()) as conn:
        ensure_customer_table(conn)
        if status:
            return list(conn.execute('SELECT * FROM customers WHERE status = ? ORDER BY updated_at DESC LIMIT ?', (status, limit)))
        return list(conn.execute('SELECT * FROM customers ORDER BY updated_at DESC LIMIT ?', (limit,)))


def record_customer_document(email: str, size_bytes: int) -> None:
    customer_email = canonical_customer_identity(email)
    storage_mb = max(0, size_bytes) / (1024 * 1024)
    with closing(connect()) as conn:
        ensure_customer_table(conn)
        conn.execute(
            '''
            UPDATE customers
            SET document_count = document_count + 1,
                storage_used_mb = storage_used_mb + ?,
                last_activity_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
            ''',
            (storage_mb, customer_email),
        )
        conn.commit()


def add_document(record: dict) -> None:
    customer_identity = canonical_customer_identity(record.get('customer_identity') or record['customer_email'])
    with closing(connect()) as conn:
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
        conn.commit()
    record_customer_document(customer_identity, int(record.get('size_bytes') or 0))


def mark_missing_file(document_id: int) -> None:
    with closing(connect()) as conn:
        _ensure_documents_columns(conn)
        conn.execute(
            'UPDATE documents SET missing_file = 1 WHERE id = ?',
            (document_id,),
        )
        conn.commit()


def all_documents() -> list[sqlite3.Row]:
    with closing(connect()) as conn:
        _ensure_documents_columns(conn)
        return list(conn.execute('SELECT * FROM documents ORDER BY id'))


def documents_for_consistency_check(*, limit: int | None = None, since_id: int | None = None) -> list[sqlite3.Row]:
    sql = 'SELECT * FROM documents'
    params: list[int] = []
    if since_id is not None:
        sql += ' WHERE id > ?'
        params.append(since_id)
    sql += ' ORDER BY id'
    if limit is not None:
        sql += ' LIMIT ?'
        params.append(limit)

    with closing(connect()) as conn:
        _ensure_documents_columns(conn)
        return list(conn.execute(sql, params))


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

    with closing(connect()) as conn:
        _ensure_documents_columns(conn)
        return list(conn.execute(sql, params))
