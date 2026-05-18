from __future__ import annotations

import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import settings
from .utils import sanitize_for_log


REQUIRED_TABLES = {'documents', 'rate_limit_events', 'rate_limit_cooldowns'}


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    size: int
    created_at: str


@dataclass(frozen=True)
class RestoreResult:
    backup_path: Path
    database_path: Path
    dry_run: bool
    restored: bool
    message: str


def _timestamp() -> str:
    return datetime.now().strftime('%Y%m%d-%H%M%S-%f')


def _safe_reason(reason: str) -> str:
    clean = ''.join(char if char.isalnum() or char in {'-', '_'} else '_' for char in (reason or 'manual').lower())
    return clean.strip('_') or 'manual'


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f'file:{path.resolve().as_posix()}?mode=ro'
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def validate_database(path: Path, *, require_tables: bool = True) -> tuple[bool, str]:
    if not path.exists():
        return False, 'database file does not exist'
    if path.stat().st_size == 0:
        return False, 'database file is empty'

    try:
        with closing(_connect_readonly(path)) as conn:
            integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
            if integrity != 'ok':
                return False, f'integrity check failed: {integrity}'

            if require_tables:
                tables = {
                    row['name']
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                    )
                }
                missing = sorted(REQUIRED_TABLES - tables)
                if missing:
                    return False, f'missing required tables: {", ".join(missing)}'
    except sqlite3.DatabaseError as exc:
        return False, f'database validation failed: {sanitize_for_log(exc)}'

    return True, 'ok'


def list_backups(backup_dir: Path | None = None) -> list[BackupInfo]:
    folder = backup_dir or settings.backup_dir
    if not folder.exists():
        return []

    backups: list[BackupInfo] = []
    for path in sorted(folder.glob('bewaarhet-*.sqlite3'), key=lambda item: item.stat().st_mtime, reverse=True):
        backups.append(
            BackupInfo(
                path=path,
                size=path.stat().st_size,
                created_at=datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='seconds'),
            )
        )
    return backups


def rotate_backups(backup_dir: Path | None = None, *, keep_latest: int | None = None) -> None:
    keep = settings.backup_keep_latest if keep_latest is None else keep_latest
    if keep < 1:
        keep = 1

    for backup in list_backups(backup_dir)[keep:]:
        backup.path.unlink(missing_ok=True)


def create_backup(
    *,
    database_path: Path | None = None,
    backup_dir: Path | None = None,
    keep_latest: int | None = None,
    reason: str = 'manual',
    require_tables: bool = True,
) -> Path:
    source = database_path or settings.database_path
    folder = backup_dir or settings.backup_dir
    folder.mkdir(parents=True, exist_ok=True)

    valid, message = validate_database(source, require_tables=require_tables)
    if not valid:
        raise RuntimeError(f'Backup aborted: {message}')

    final_path = folder / f'bewaarhet-{_timestamp()}-{_safe_reason(reason)}.sqlite3'
    temp_path = final_path.with_suffix('.tmp')

    try:
        with closing(_connect_readonly(source)) as src, closing(sqlite3.connect(temp_path)) as dst:
            src.backup(dst)
            dst.commit()
        valid_backup, backup_message = validate_database(temp_path, require_tables=require_tables)
        if not valid_backup:
            raise RuntimeError(f'Backup validation failed: {backup_message}')
        temp_path.replace(final_path)
        rotate_backups(folder, keep_latest=keep_latest)
    finally:
        temp_path.unlink(missing_ok=True)

    print(
        "SQLite backup created"
        f" | source={sanitize_for_log(source)}"
        f" | backup={sanitize_for_log(final_path)}"
        f" | reason={sanitize_for_log(reason)}"
    )
    return final_path


def restore_backup(
    backup_path: Path,
    *,
    database_path: Path | None = None,
    dry_run: bool = False,
    confirm: bool = False,
    backup_current: bool = True,
) -> RestoreResult:
    source = backup_path
    target = database_path or settings.database_path

    valid, message = validate_database(source)
    if not valid:
        raise RuntimeError(f'Restore aborted: {message}')

    if dry_run:
        return RestoreResult(source, target, True, False, 'backup validation passed; no files changed')

    if not confirm:
        raise RuntimeError('Restore requires confirm=True because it overwrites the active database')

    target.parent.mkdir(parents=True, exist_ok=True)
    if backup_current and target.exists() and target.stat().st_size > 0:
        create_backup(database_path=target, backup_dir=settings.backup_dir, reason='pre-restore')

    temp_path = target.with_name(f'.{target.name}.restore.tmp')
    try:
        with closing(_connect_readonly(source)) as src, closing(sqlite3.connect(temp_path)) as dst:
            src.backup(dst)
            dst.commit()
        valid_temp, temp_message = validate_database(temp_path)
        if not valid_temp:
            raise RuntimeError(f'Restored copy validation failed: {temp_message}')
        temp_path.replace(target)
    finally:
        temp_path.unlink(missing_ok=True)

    print(
        "SQLite backup restored"
        f" | backup={sanitize_for_log(source)}"
        f" | target={sanitize_for_log(target)}"
    )
    return RestoreResult(source, target, False, True, 'restore completed')


def copy_backup_to_folder(backup_path: Path, destination_folder: Path) -> Path:
    destination_folder.mkdir(parents=True, exist_ok=True)
    destination = destination_folder / backup_path.name
    shutil.copy2(backup_path, destination)
    return destination
