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
    account_id INTEGER DEFAULT NULL,
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
CREATE INDEX IF NOT EXISTS idx_documents_account ON documents(account_id);
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

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT DEFAULT NULL,
    status TEXT NOT NULL DEFAULT 'pending_verification' CHECK(status IN ('pending_verification', 'trial', 'active', 'past_due', 'canceled', 'blocked')),
    plan TEXT NOT NULL DEFAULT 'trial',
    primary_email TEXT NOT NULL UNIQUE,
    safe_account_folder TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    document_count INTEGER NOT NULL DEFAULT 0,
    storage_used_mb REAL NOT NULL DEFAULT 0,
    last_activity_at TEXT DEFAULT NULL,
    trial_started_at TEXT DEFAULT NULL,
    trial_ends_at TEXT DEFAULT NULL,
    billing_provider TEXT DEFAULT NULL,
    billing_customer_id TEXT DEFAULT NULL,
    subscription_id TEXT DEFAULT NULL,
    subscription_status TEXT NOT NULL DEFAULT 'none',
    payment_started_at TEXT DEFAULT NULL,
    paid_until TEXT DEFAULT NULL,
    cancelled_at TEXT DEFAULT NULL,
    notes TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
CREATE INDEX IF NOT EXISTS idx_accounts_primary_email ON accounts(primary_email);

CREATE TABLE IF NOT EXISTS account_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    email TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL DEFAULT 'hoofd',
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'verified', 'disabled')),
    can_store INTEGER NOT NULL DEFAULT 1,
    can_search INTEGER NOT NULL DEFAULT 1,
    can_manage INTEGER NOT NULL DEFAULT 0,
    is_primary INTEGER NOT NULL DEFAULT 0,
    verified_at TEXT DEFAULT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(account_id) REFERENCES accounts(id)
);

CREATE INDEX IF NOT EXISTS idx_account_emails_account ON account_emails(account_id);
CREATE INDEX IF NOT EXISTS idx_account_emails_status ON account_emails(status);

CREATE TABLE IF NOT EXISTS account_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    provider TEXT NOT NULL DEFAULT 'mollie',
    provider_payment_id TEXT NOT NULL UNIQUE,
    provider_customer_id TEXT DEFAULT NULL,
    provider_subscription_id TEXT DEFAULT NULL,
    purpose TEXT NOT NULL DEFAULT 'first_payment',
    status TEXT NOT NULL DEFAULT 'open',
    checkout_url TEXT DEFAULT NULL,
    amount_value TEXT DEFAULT NULL,
    currency TEXT DEFAULT 'EUR',
    raw_status TEXT DEFAULT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(account_id) REFERENCES accounts(id)
);

CREATE INDEX IF NOT EXISTS idx_account_payments_account ON account_payments(account_id);
CREATE INDEX IF NOT EXISTS idx_account_payments_status ON account_payments(status);
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
    'account_id',
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
    if not {'rate_limit_events', 'rate_limit_cooldowns', 'customers', 'accounts', 'account_emails', 'account_payments'}.issubset(tables):
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
    if 'account_id' not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN account_id INTEGER DEFAULT NULL")
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


def _ensure_accounts_columns(conn: sqlite3.Connection) -> None:
    existing_columns = {row['name'] for row in conn.execute("PRAGMA table_info(accounts)")}
    columns = {
        'subscription_status': "ALTER TABLE accounts ADD COLUMN subscription_status TEXT NOT NULL DEFAULT 'none'",
        'payment_started_at': "ALTER TABLE accounts ADD COLUMN payment_started_at TEXT DEFAULT NULL",
        'paid_until': "ALTER TABLE accounts ADD COLUMN paid_until TEXT DEFAULT NULL",
        'cancelled_at': "ALTER TABLE accounts ADD COLUMN cancelled_at TEXT DEFAULT NULL",
    }
    for column, statement in columns.items():
        if column not in existing_columns:
            conn.execute(statement)


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
        ensure_account_tables(conn)
        migrate_customers_to_accounts(conn)
        backfill_document_account_ids(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_domain_search ON documents(customer_email, domain)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_customer_identity ON documents(customer_identity)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_account ON documents(account_id)")
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


def ensure_account_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT DEFAULT NULL,
            status TEXT NOT NULL DEFAULT 'pending_verification' CHECK(status IN ('pending_verification', 'trial', 'active', 'past_due', 'canceled', 'blocked')),
            plan TEXT NOT NULL DEFAULT 'trial',
            primary_email TEXT NOT NULL UNIQUE,
            safe_account_folder TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            document_count INTEGER NOT NULL DEFAULT 0,
            storage_used_mb REAL NOT NULL DEFAULT 0,
            last_activity_at TEXT DEFAULT NULL,
            trial_started_at TEXT DEFAULT NULL,
            trial_ends_at TEXT DEFAULT NULL,
            billing_provider TEXT DEFAULT NULL,
            billing_customer_id TEXT DEFAULT NULL,
            subscription_id TEXT DEFAULT NULL,
            subscription_status TEXT NOT NULL DEFAULT 'none',
            payment_started_at TEXT DEFAULT NULL,
            paid_until TEXT DEFAULT NULL,
            cancelled_at TEXT DEFAULT NULL,
            notes TEXT DEFAULT NULL
        )
        '''
    )
    _ensure_accounts_columns(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_accounts_primary_email ON accounts(primary_email)")
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS account_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            email TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL DEFAULT 'hoofd',
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'verified', 'disabled')),
            can_store INTEGER NOT NULL DEFAULT 1,
            can_search INTEGER NOT NULL DEFAULT 1,
            can_manage INTEGER NOT NULL DEFAULT 0,
            is_primary INTEGER NOT NULL DEFAULT 0,
            verified_at TEXT DEFAULT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        )
        '''
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_account_emails_account ON account_emails(account_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_account_emails_status ON account_emails(status)")
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS account_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            provider TEXT NOT NULL DEFAULT 'mollie',
            provider_payment_id TEXT NOT NULL UNIQUE,
            provider_customer_id TEXT DEFAULT NULL,
            provider_subscription_id TEXT DEFAULT NULL,
            purpose TEXT NOT NULL DEFAULT 'first_payment',
            status TEXT NOT NULL DEFAULT 'open',
            checkout_url TEXT DEFAULT NULL,
            amount_value TEXT DEFAULT NULL,
            currency TEXT DEFAULT 'EUR',
            raw_status TEXT DEFAULT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        )
        '''
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_account_payments_account ON account_payments(account_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_account_payments_status ON account_payments(status)")


def migrate_customers_to_accounts(conn: sqlite3.Connection) -> None:
    ensure_customer_table(conn)
    ensure_account_tables(conn)
    rows = list(conn.execute('SELECT * FROM customers ORDER BY id'))
    for row in rows:
        email = canonical_customer_identity(row['email'])
        if not email:
            continue
        account = conn.execute('SELECT * FROM accounts WHERE primary_email = ?', (email,)).fetchone()
        safe_folder = email.replace('@', '_at_')
        if account is None:
            conn.execute(
                '''
                INSERT INTO accounts
                (name, status, primary_email, safe_account_folder, created_at, updated_at,
                 document_count, storage_used_mb, last_activity_at, trial_started_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    row['name'], row['status'], email, safe_folder, row['created_at'], row['updated_at'],
                    row['document_count'], row['storage_used_mb'], row['last_activity_at'],
                    row['trial_started_at'], row['notes'],
                ),
            )
            account_id = int(conn.execute('SELECT last_insert_rowid()').fetchone()[0])
        else:
            account_id = int(account['id'])
        email_row = conn.execute('SELECT * FROM account_emails WHERE email = ?', (email,)).fetchone()
        if email_row is None:
            email_status = 'verified' if row['status'] in {'trial', 'active'} else 'pending'
            conn.execute(
                '''
                INSERT INTO account_emails
                (account_id, email, label, status, can_store, can_search, can_manage, is_primary, verified_at)
                VALUES (?, ?, 'hoofd', ?, 1, 1, 1, 1, CASE WHEN ? = 'verified' THEN CURRENT_TIMESTAMP ELSE NULL END)
                ''',
                (account_id, email, email_status, email_status),
            )


def backfill_document_account_ids(conn: sqlite3.Connection) -> None:
    _ensure_documents_columns(conn)
    ensure_account_tables(conn)
    rows = list(conn.execute(
        '''
        SELECT d.id, d.customer_email
        FROM documents d
        WHERE d.account_id IS NULL
        '''
    ))
    for row in rows:
        email = canonical_customer_identity(row['customer_email'])
        email_row = conn.execute('SELECT account_id FROM account_emails WHERE email = ?', (email,)).fetchone()
        if email_row is None:
            continue
        conn.execute('UPDATE documents SET account_id = ? WHERE id = ?', (email_row['account_id'], row['id']))


def get_customer(email: str) -> sqlite3.Row | None:
    customer_email = canonical_customer_identity(email)
    with closing(connect()) as conn:
        ensure_customer_table(conn)
        return conn.execute('SELECT * FROM customers WHERE email = ?', (customer_email,)).fetchone()


def get_account_for_email(email: str) -> sqlite3.Row | None:
    customer_email = canonical_customer_identity(email)
    with closing(connect()) as conn:
        ensure_account_tables(conn)
        return conn.execute(
            '''
            SELECT a.*
            FROM accounts a
            JOIN account_emails ae ON ae.account_id = a.id
            WHERE ae.email = ?
            ''',
            (customer_email,),
        ).fetchone()


def get_account_by_id(account_id: int) -> sqlite3.Row | None:
    with closing(connect()) as conn:
        ensure_account_tables(conn)
        return conn.execute('SELECT * FROM accounts WHERE id = ?', (account_id,)).fetchone()


def set_account_billing_status(
    account_id: int,
    *,
    status: str | None = None,
    subscription_status: str | None = None,
    billing_provider: str | None = None,
    billing_customer_id: str | None = None,
    subscription_id: str | None = None,
    payment_started: bool = False,
    paid_until: str | None = None,
    cancelled: bool = False,
    notes: str | None = None,
) -> sqlite3.Row:
    if status and status not in {'pending_verification', 'trial', 'active', 'past_due', 'canceled', 'blocked'}:
        raise ValueError(f'unsupported account status: {status}')
    with closing(connect()) as conn:
        ensure_account_tables(conn)
        conn.execute(
            '''
            UPDATE accounts
            SET status = COALESCE(?, status),
                subscription_status = COALESCE(?, subscription_status),
                billing_provider = COALESCE(?, billing_provider),
                billing_customer_id = COALESCE(?, billing_customer_id),
                subscription_id = COALESCE(?, subscription_id),
                payment_started_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE payment_started_at END,
                paid_until = COALESCE(?, paid_until),
                cancelled_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE cancelled_at END,
                notes = COALESCE(?, notes),
                updated_at = CURRENT_TIMESTAMP,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''',
            (
                status, subscription_status, billing_provider, billing_customer_id, subscription_id,
                int(payment_started), paid_until, int(cancelled), notes, account_id,
            ),
        )
        if status in {'trial', 'active', 'blocked'}:
            account = conn.execute('SELECT primary_email FROM accounts WHERE id = ?', (account_id,)).fetchone()
            if account is not None:
                legacy_status = status
                conn.execute(
                    '''
                    UPDATE customers
                    SET status = ?,
                        updated_at = CURRENT_TIMESTAMP,
                        last_activity_at = CURRENT_TIMESTAMP
                    WHERE email = ?
                    ''',
                    (legacy_status, account['primary_email']),
                )
        conn.commit()
        row = conn.execute('SELECT * FROM accounts WHERE id = ?', (account_id,)).fetchone()
        if row is None:
            raise RuntimeError('account billing update failed')
        return row


def record_account_payment(
    *,
    account_id: int,
    provider_payment_id: str,
    provider_customer_id: str | None = None,
    provider_subscription_id: str | None = None,
    purpose: str = 'first_payment',
    status: str = 'open',
    checkout_url: str | None = None,
    amount_value: str | None = None,
    currency: str = 'EUR',
    raw_status: str | None = None,
) -> sqlite3.Row:
    with closing(connect()) as conn:
        ensure_account_tables(conn)
        conn.execute(
            '''
            INSERT INTO account_payments
            (account_id, provider, provider_payment_id, provider_customer_id, provider_subscription_id,
             purpose, status, checkout_url, amount_value, currency, raw_status)
            VALUES (?, 'mollie', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_payment_id) DO UPDATE SET
                provider_customer_id = COALESCE(excluded.provider_customer_id, account_payments.provider_customer_id),
                provider_subscription_id = COALESCE(excluded.provider_subscription_id, account_payments.provider_subscription_id),
                status = excluded.status,
                checkout_url = COALESCE(excluded.checkout_url, account_payments.checkout_url),
                amount_value = COALESCE(excluded.amount_value, account_payments.amount_value),
                currency = COALESCE(excluded.currency, account_payments.currency),
                raw_status = COALESCE(excluded.raw_status, account_payments.raw_status),
                updated_at = CURRENT_TIMESTAMP
            ''',
            (
                account_id, provider_payment_id, provider_customer_id, provider_subscription_id,
                purpose, status, checkout_url, amount_value, currency, raw_status,
            ),
        )
        conn.commit()
        row = conn.execute('SELECT * FROM account_payments WHERE provider_payment_id = ?', (provider_payment_id,)).fetchone()
        if row is None:
            raise RuntimeError('payment record failed')
        return row


def get_account_payment(provider_payment_id: str) -> sqlite3.Row | None:
    with closing(connect()) as conn:
        ensure_account_tables(conn)
        return conn.execute('SELECT * FROM account_payments WHERE provider_payment_id = ?', (provider_payment_id,)).fetchone()


def update_account_payment_status(
    provider_payment_id: str,
    *,
    status: str,
    raw_status: str | None = None,
    provider_subscription_id: str | None = None,
) -> sqlite3.Row | None:
    with closing(connect()) as conn:
        ensure_account_tables(conn)
        conn.execute(
            '''
            UPDATE account_payments
            SET status = ?,
                raw_status = COALESCE(?, raw_status),
                provider_subscription_id = COALESCE(?, provider_subscription_id),
                updated_at = CURRENT_TIMESTAMP
            WHERE provider_payment_id = ?
            ''',
            (status, raw_status, provider_subscription_id, provider_payment_id),
        )
        conn.commit()
        return conn.execute('SELECT * FROM account_payments WHERE provider_payment_id = ?', (provider_payment_id,)).fetchone()


def extend_account_trial(email: str, trial_ends_at: str, *, notes: str | None = None) -> sqlite3.Row:
    account = get_account_for_email(email)
    if account is None:
        raise ValueError('account not found')
    with closing(connect()) as conn:
        ensure_account_tables(conn)
        conn.execute(
            '''
            UPDATE accounts
            SET status = 'trial',
                trial_started_at = COALESCE(trial_started_at, CURRENT_TIMESTAMP),
                trial_ends_at = ?,
                notes = COALESCE(?, notes),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''',
            (trial_ends_at, notes, account['id']),
        )
        conn.commit()
        row = conn.execute('SELECT * FROM accounts WHERE id = ?', (account['id'],)).fetchone()
        if row is None:
            raise RuntimeError('trial extension failed')
        return row


def get_account_email(email: str) -> sqlite3.Row | None:
    customer_email = canonical_customer_identity(email)
    with closing(connect()) as conn:
        ensure_account_tables(conn)
        return conn.execute('SELECT * FROM account_emails WHERE email = ?', (customer_email,)).fetchone()


def account_context_for_email(email: str) -> dict | None:
    customer_email = canonical_customer_identity(email)
    with closing(connect()) as conn:
        ensure_account_tables(conn)
        row = conn.execute(
            '''
            SELECT
                a.id AS account_id,
                a.status AS account_status,
                a.primary_email,
                a.safe_account_folder,
                a.document_count,
                a.storage_used_mb,
                ae.email AS sender_email,
                ae.status AS email_status,
                ae.label AS email_label,
                ae.can_store,
                ae.can_search,
                ae.can_manage
            FROM accounts a
            JOIN account_emails ae ON ae.account_id = a.id
            WHERE ae.email = ?
            ''',
            (customer_email,),
        ).fetchone()
        return dict(row) if row else None


def add_account_email(
    owner_email: str,
    new_email: str,
    *,
    label: str = 'extra',
    can_store: bool = True,
    can_search: bool = True,
    can_manage: bool = False,
) -> sqlite3.Row:
    owner_identity = canonical_customer_identity(owner_email)
    new_identity = canonical_customer_identity(new_email)
    if not owner_identity or not new_identity:
        raise ValueError('owner_email and new_email are required')
    with closing(connect()) as conn:
        ensure_account_tables(conn)
        owner = conn.execute(
            '''
            SELECT a.*
            FROM accounts a
            JOIN account_emails ae ON ae.account_id = a.id
            WHERE ae.email = ? AND ae.status = 'verified' AND ae.can_manage = 1
            ''',
            (owner_identity,),
        ).fetchone()
        if owner is None:
            raise ValueError('owner email is not allowed to manage this account')
        existing = conn.execute('SELECT * FROM account_emails WHERE email = ?', (new_identity,)).fetchone()
        if existing is not None:
            raise ValueError('email address already belongs to an account')
        conn.execute(
            '''
            INSERT INTO account_emails
            (account_id, email, label, status, can_store, can_search, can_manage, is_primary)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, 0)
            ''',
            (owner['id'], new_identity, label, int(can_store), int(can_search), int(can_manage)),
        )
        conn.commit()
        row = conn.execute('SELECT * FROM account_emails WHERE email = ?', (new_identity,)).fetchone()
        if row is None:
            raise RuntimeError('account email creation failed')
        return row


def ensure_customer(email: str, *, name: str | None = None) -> tuple[sqlite3.Row, bool]:
    customer_email = canonical_customer_identity(email)
    if not customer_email:
        raise ValueError('customer email is required')
    with closing(connect()) as conn:
        ensure_customer_table(conn)
        ensure_account_tables(conn)
        existing = conn.execute('SELECT * FROM customers WHERE email = ?', (customer_email,)).fetchone()
        if existing:
            migrate_customers_to_accounts(conn)
            conn.commit()
            return existing, False
        existing_account_email = conn.execute(
            '''
            SELECT a.status, a.name, a.document_count, a.storage_used_mb, a.last_activity_at, a.trial_started_at, ae.status AS email_status
            FROM account_emails ae
            JOIN accounts a ON a.id = ae.account_id
            WHERE ae.email = ?
            ''',
            (customer_email,),
        ).fetchone()
        if existing_account_email is not None:
            status = str(existing_account_email['status'] or 'pending_verification')
            if existing_account_email['email_status'] == 'pending':
                status = 'pending_verification'
            if existing_account_email['email_status'] == 'disabled':
                status = 'blocked'
            legacy_status = status if status in {'pending_verification', 'trial', 'active', 'blocked'} else 'blocked'
            conn.execute(
                '''
                INSERT INTO customers
                (email, name, status, document_count, storage_used_mb, last_activity_at, trial_started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    customer_email,
                    existing_account_email['name'],
                    legacy_status,
                    existing_account_email['document_count'],
                    existing_account_email['storage_used_mb'],
                    existing_account_email['last_activity_at'],
                    existing_account_email['trial_started_at'],
                ),
            )
            conn.commit()
            created_from_account = conn.execute('SELECT * FROM customers WHERE email = ?', (customer_email,)).fetchone()
            if created_from_account is None:
                raise RuntimeError('customer compatibility creation failed')
            return created_from_account, False
        conn.execute(
            '''
            INSERT INTO customers
            (email, name, status, trial_started_at, last_activity_at)
            VALUES (?, ?, 'pending_verification', NULL, CURRENT_TIMESTAMP)
            ''',
            (customer_email, name),
        )
        safe_folder = customer_email.replace('@', '_at_')
        conn.execute(
            '''
            INSERT INTO accounts
            (name, status, primary_email, safe_account_folder, last_activity_at)
            VALUES (?, 'pending_verification', ?, ?, CURRENT_TIMESTAMP)
            ''',
            (name, customer_email, safe_folder),
        )
        account_id = int(conn.execute('SELECT last_insert_rowid()').fetchone()[0])
        conn.execute(
            '''
            INSERT INTO account_emails
            (account_id, email, label, status, can_store, can_search, can_manage, is_primary)
            VALUES (?, ?, 'hoofd', 'pending', 1, 1, 1, 1)
            ''',
            (account_id, customer_email),
        )
        conn.commit()
        created = conn.execute('SELECT * FROM customers WHERE email = ?', (customer_email,)).fetchone()
        if created is None:
            raise RuntimeError('customer creation failed')
        return created, True


def update_customer_status(email: str, status: str, *, name: str | None = None, notes: str | None = None) -> sqlite3.Row:
    if status not in {'pending_verification', 'trial', 'active', 'past_due', 'canceled', 'blocked'}:
        raise ValueError(f'unsupported customer status: {status}')
    legacy_customer_status = status if status in {'pending_verification', 'trial', 'active', 'blocked'} else 'blocked'
    customer_email = canonical_customer_identity(email)
    with closing(connect()) as conn:
        ensure_customer_table(conn)
        ensure_account_tables(conn)
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
            (customer_email, name, legacy_customer_status, legacy_customer_status, notes),
        )
        safe_folder = customer_email.replace('@', '_at_')
        conn.execute(
            '''
            INSERT INTO accounts (name, status, primary_email, safe_account_folder, last_activity_at, trial_started_at, notes)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CASE WHEN ? = 'trial' THEN CURRENT_TIMESTAMP ELSE NULL END, ?)
            ON CONFLICT(primary_email) DO UPDATE SET
                status = excluded.status,
                name = COALESCE(excluded.name, accounts.name),
                notes = COALESCE(excluded.notes, accounts.notes),
                updated_at = CURRENT_TIMESTAMP,
                last_activity_at = CURRENT_TIMESTAMP,
                trial_started_at = CASE
                    WHEN excluded.status = 'trial' AND accounts.trial_started_at IS NULL THEN CURRENT_TIMESTAMP
                    WHEN excluded.status = 'pending_verification' THEN NULL
                    ELSE accounts.trial_started_at
                END
            ''',
            (name, status, customer_email, safe_folder, status, notes),
        )
        account = conn.execute('SELECT * FROM accounts WHERE primary_email = ?', (customer_email,)).fetchone()
        if account:
            email_status = 'verified' if status in {'trial', 'active', 'past_due', 'canceled'} else 'pending'
            if status == 'blocked':
                email_status = 'disabled'
            conn.execute(
                '''
                INSERT INTO account_emails
                (account_id, email, label, status, can_store, can_search, can_manage, is_primary, verified_at)
                VALUES (?, ?, 'hoofd', ?, 1, 1, 1, 1, CASE WHEN ? = 'verified' THEN CURRENT_TIMESTAMP ELSE NULL END)
                ON CONFLICT(email) DO UPDATE SET
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP,
                    verified_at = CASE
                        WHEN excluded.status = 'verified' AND account_emails.verified_at IS NULL THEN CURRENT_TIMESTAMP
                        ELSE account_emails.verified_at
                    END
                ''',
                (account['id'], customer_email, email_status, email_status),
            )
        conn.commit()
        row = conn.execute('SELECT * FROM customers WHERE email = ?', (customer_email,)).fetchone()
        if row is None:
            raise RuntimeError('customer status update failed')
        return row


def activate_pending_customer(email: str) -> sqlite3.Row:
    customer_email = canonical_customer_identity(email)
    with closing(connect()) as conn:
        ensure_customer_table(conn)
        ensure_account_tables(conn)
        trial_days = max(1, int(getattr(settings, 'trial_days', 14)))
        row = conn.execute('SELECT * FROM customers WHERE email = ?', (customer_email,)).fetchone()
        email_row = conn.execute('SELECT * FROM account_emails WHERE email = ?', (customer_email,)).fetchone()
        account = None
        if email_row is not None:
            account = conn.execute('SELECT * FROM accounts WHERE id = ?', (email_row['account_id'],)).fetchone()
        if row is None and email_row is None:
            raise ValueError('activation token is invalid or already used')
        if (
            (row is None or row['status'] != 'pending_verification')
            and (email_row is None or email_row['status'] != 'pending')
        ):
            raise ValueError('activation token is invalid or already used')
        if row is not None and row['status'] == 'pending_verification':
            conn.execute(
                '''
                UPDATE customers
                SET status = 'trial',
                    trial_started_at = COALESCE(trial_started_at, CURRENT_TIMESTAMP),
                    updated_at = CURRENT_TIMESTAMP,
                    last_activity_at = CURRENT_TIMESTAMP
                WHERE email = ? AND status = 'pending_verification'
                ''',
                (customer_email,),
            )
        if email_row is not None and email_row['status'] == 'pending':
            conn.execute(
                '''
                UPDATE account_emails
                SET status = 'verified',
                    verified_at = COALESCE(verified_at, CURRENT_TIMESTAMP),
                    updated_at = CURRENT_TIMESTAMP
                WHERE email = ? AND status = 'pending'
                ''',
                (customer_email,),
            )
        if account is not None and account['status'] == 'pending_verification':
            conn.execute(
                '''
                UPDATE accounts
                SET status = 'trial',
                    trial_started_at = COALESCE(trial_started_at, CURRENT_TIMESTAMP),
                    trial_ends_at = COALESCE(trial_ends_at, datetime('now', '+' || ? || ' days')),
                    updated_at = CURRENT_TIMESTAMP,
                    last_activity_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'pending_verification'
                ''',
                (trial_days, account['id']),
            )
        conn.commit()
        activated = conn.execute('SELECT * FROM customers WHERE email = ?', (customer_email,)).fetchone()
        if activated is not None:
            return activated
        email_row = conn.execute('SELECT * FROM account_emails WHERE email = ?', (customer_email,)).fetchone()
        if email_row is None or email_row['status'] != 'verified':
            raise RuntimeError('account email activation failed')
        account = conn.execute('SELECT * FROM accounts WHERE id = ?', (email_row['account_id'],)).fetchone()
        if account is None:
            raise RuntimeError('account activation failed')
        return account


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
        ensure_account_tables(conn)
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
        email_row = conn.execute('SELECT account_id FROM account_emails WHERE email = ?', (customer_email,)).fetchone()
        if email_row is not None:
            conn.execute(
                '''
                UPDATE accounts
                SET document_count = document_count + 1,
                    storage_used_mb = storage_used_mb + ?,
                    last_activity_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (storage_mb, email_row['account_id']),
            )
        conn.commit()


def add_document(record: dict) -> None:
    customer_identity = canonical_customer_identity(record.get('customer_identity') or record['customer_email'])
    account_id = record.get('account_id')
    if account_id is None:
        context = account_context_for_email(customer_identity)
        if context:
            account_id = context['account_id']
    with closing(connect()) as conn:
        _ensure_documents_columns(conn)
        conn.execute(
            '''
            INSERT OR REPLACE INTO documents
            (account_id, customer_identity, customer_email, safe_customer_folder, category, filename, date_received,
             dropbox_path, original_filename, document_date, domain, supplier, purpose, title,
             ocr_preview, ocr_text, year, month)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                account_id,
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
    context = account_context_for_email(customer_identity)
    account_id = None
    if (
        context
        and context.get('email_status') == 'verified'
        and context.get('account_status') in {'trial', 'active', 'past_due'}
        and int(context.get('can_search') or 0)
    ):
        account_id = context['account_id']

    search_parts = []
    if account_id is not None:
        params: list[str | int] = [account_id, customer_identity]
        ownership_sql = '(account_id = ? OR lower(COALESCE(NULLIF(customer_identity, \'\'), customer_email)) = ?)'
    else:
        params = [customer_identity]
        ownership_sql = 'lower(COALESCE(NULLIF(customer_identity, \'\'), customer_email)) = ?'

    for term in terms:
        like = f'%{term}%'
        search_parts.append(
            '(lower(filename) LIKE ? OR lower(category) LIKE ? OR lower(domain) LIKE ? OR lower(supplier) LIKE ? OR lower(purpose) LIKE ? OR lower(title) LIKE ? OR lower(ocr_preview) LIKE ? OR lower(ocr_text) LIKE ? OR lower(dropbox_path) LIKE ? OR year LIKE ? OR month LIKE ?)'
        )
        params.extend([like, like, like, like, like, like, like, like, like, like, like])

    sql = f'''
        SELECT * FROM documents
        WHERE {ownership_sql}
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
