from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _csv(value: str) -> set[str]:
    items = set()
    for item in value.split(','):
        item = item.strip().lower()
        if not item:
            continue
        items.add(item if item.startswith('.') else f'.{item}')
    return items


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on', 'ja'}


DEFAULT_ALLOWED_EXTENSIONS = (
    '.pdf,.doc,.docx,.odt,'
    '.xls,.xlsx,.ods,.txt,.csv,.rtf,'
    '.jpg,.jpeg,.png,.gif,.bmp,.tiff,'
    '.zip'
)

DEFAULT_TRIAL_ALLOWED_EXTENSIONS = DEFAULT_ALLOWED_EXTENSIONS


def _path_from_env(name: str, default: Path | str) -> Path:
    return Path(os.getenv(name, str(default))).expanduser().resolve()


DEFAULT_DATA_DIR = _path_from_env('DATA_DIR', 'data')


@dataclass(frozen=True)
class Settings:
    zoho_email: str = os.getenv('ZOHO_EMAIL', 'service@bewaarhet.nl')
    zoho_imap_host: str = os.getenv('ZOHO_IMAP_HOST', 'imap.zoho.eu')
    zoho_imap_port: int = int(os.getenv('ZOHO_IMAP_PORT', '993'))
    zoho_smtp_host: str = os.getenv('ZOHO_SMTP_HOST', 'smtp.zoho.eu')
    zoho_smtp_port: int = int(os.getenv('ZOHO_SMTP_PORT', '587'))
    zoho_app_password: str = os.getenv('ZOHO_APP_PASSWORD', '')

    dropbox_app_key: str = os.getenv('DROPBOX_APP_KEY', '')
    dropbox_app_secret: str = os.getenv('DROPBOX_APP_SECRET', '')
    dropbox_refresh_token: str = os.getenv('DROPBOX_REFRESH_TOKEN', '')
    dropbox_base_path: str = os.getenv('DROPBOX_BASE_PATH', '/Bewaar het/Klanten')

    ocr_space_api_key: str = os.getenv('OCR_SPACE_API_KEY', '')
    ocr_space_language: str = os.getenv('OCR_SPACE_LANGUAGE', 'dut')

    openai_api_key: str = os.getenv('OPENAI_API_KEY', '')
    openai_model: str = os.getenv('OPENAI_MODEL', 'gpt-5-mini')

    data_dir: Path = DEFAULT_DATA_DIR
    database_path: Path = _path_from_env('DATABASE_PATH', DEFAULT_DATA_DIR / 'bewaarhet.sqlite3')
    backup_dir: Path = _path_from_env('BACKUP_DIR', DEFAULT_DATA_DIR / 'backups')
    log_dir: Path = _path_from_env('LOG_DIR', DEFAULT_DATA_DIR / 'logs')
    backup_keep_latest: int = int(os.getenv('BACKUP_KEEP_LATEST', '14'))
    dropbox_timeout_seconds: int = int(os.getenv('DROPBOX_TIMEOUT_SECONDS', '15'))
    consistency_log_every: int = int(os.getenv('CONSISTENCY_LOG_EVERY', '10'))
    consistency_slow_threshold_seconds: float = float(os.getenv('CONSISTENCY_SLOW_THRESHOLD_SECONDS', '2.0'))

    max_attachment_mb: int = int(os.getenv('MAX_ATTACHMENT_MB', '15'))
    max_file_size_mb: int = int(os.getenv('MAX_FILE_SIZE_MB', os.getenv('MAX_ATTACHMENT_MB', '15')))
    allowed_extensions: set[str] = None  # type: ignore[assignment]
    search_result_limit: int = int(os.getenv('SEARCH_RESULT_LIMIT', '10'))
    poll_seconds: int = int(os.getenv('POLL_SECONDS', '60'))
    customer_onboarding_enabled: bool = _bool_env('CUSTOMER_ONBOARDING_ENABLED', True)
    max_trial_documents: int = int(os.getenv('MAX_TRIAL_DOCUMENTS', '10'))
    max_trial_storage_mb: int = int(os.getenv('MAX_TRIAL_STORAGE_MB', '100'))
    max_trial_file_size_mb: int = int(os.getenv('MAX_TRIAL_FILE_SIZE_MB', os.getenv('MAX_FILE_SIZE_MB', os.getenv('MAX_ATTACHMENT_MB', '15'))))
    max_trial_mails_per_hour: int = int(os.getenv('MAX_TRIAL_MAILS_PER_HOUR', '20'))
    max_trial_documents_per_day: int = int(os.getenv('MAX_TRIAL_DOCUMENTS_PER_DAY', '25'))
    trial_allowed_extensions: set[str] = None  # type: ignore[assignment]
    welcome_email_subject: str = os.getenv('WELCOME_EMAIL_SUBJECT', 'Welkom bij Bewaarhet')
    public_site_url: str = os.getenv('PUBLIC_SITE_URL', 'https://bewaarhet.nl').rstrip('/')
    faq_url: str = os.getenv('FAQ_URL', '').strip()
    activation_url: str = os.getenv('ACTIVATION_URL', '').strip()
    verification_token_secret: str = os.getenv('VERIFICATION_TOKEN_SECRET', '')
    verification_token_ttl_hours: int = int(os.getenv('VERIFICATION_TOKEN_TTL_HOURS', '72'))

    def __post_init__(self):
        configured_extensions = _csv(os.getenv('ALLOWED_EXTENSIONS', ''))
        object.__setattr__(
            self,
            'allowed_extensions',
            _csv(DEFAULT_ALLOWED_EXTENSIONS) | configured_extensions,
        )
        object.__setattr__(
            self,
            'trial_allowed_extensions',
            _csv(os.getenv('TRIAL_ALLOWED_EXTENSIONS', DEFAULT_TRIAL_ALLOWED_EXTENSIONS)),
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
