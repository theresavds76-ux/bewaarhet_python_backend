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


DEFAULT_ALLOWED_EXTENSIONS = (
    '.pdf,.jpg,.jpeg,.png,'
    '.docx,.xlsx,.csv,.txt,'
    '.zip'
)


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

    max_attachment_mb: int = int(os.getenv('MAX_ATTACHMENT_MB', '15'))
    allowed_extensions: set[str] = None  # type: ignore[assignment]
    search_result_limit: int = int(os.getenv('SEARCH_RESULT_LIMIT', '10'))
    poll_seconds: int = int(os.getenv('POLL_SECONDS', '60'))

    def __post_init__(self):
        configured_extensions = _csv(os.getenv('ALLOWED_EXTENSIONS', ''))
        object.__setattr__(
            self,
            'allowed_extensions',
            _csv(DEFAULT_ALLOWED_EXTENSIONS) | configured_extensions,
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
