from __future__ import annotations

import re
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

from .backup import create_backup
from .config import settings
from .database import all_documents, connect, init_db
from .dropbox_client import path_exists
from .utils import file_extension, safe_customer_folder, sanitize_for_log


TESTDATA_FILENAME_TERMS = (
    'test',
    'testje',
    'img_',
    'coc_',
    'dummy',
    'sample',
    'tmp',
)

UNSUPPORTED_LEGACY_EXTENSIONS = {'.webp'}
TEMP_DEV_PATH_PARTS = {'tmp', 'temp', 'dev', 'development', 'sandbox'}


@dataclass(frozen=True)
class CleanupFinding:
    document_id: int
    filename: str
    dropbox_path: str
    reason: str


@dataclass(frozen=True)
class CleanupReport:
    total_records: int = 0
    orphaned_records: list[CleanupFinding] = field(default_factory=list)
    missing_dropbox_files: list[CleanupFinding] = field(default_factory=list)
    unsupported_legacy_records: list[CleanupFinding] = field(default_factory=list)
    temporary_dev_path_records: list[CleanupFinding] = field(default_factory=list)
    duplicate_records: list[CleanupFinding] = field(default_factory=list)
    ownership_failed_records: list[CleanupFinding] = field(default_factory=list)
    testdata_records: list[CleanupFinding] = field(default_factory=list)
    dropbox_errors: list[CleanupFinding] = field(default_factory=list)
    approximate_db_reduction_bytes: int = 0

    @property
    def orphaned_cleanup_ids(self) -> set[int]:
        return {
            finding.document_id
            for finding in [
                *self.orphaned_records,
                *self.missing_dropbox_files,
                *self.temporary_dev_path_records,
                *self.ownership_failed_records,
            ]
        }

    @property
    def testdata_cleanup_ids(self) -> set[int]:
        return {
            finding.document_id
            for finding in [
                *self.testdata_records,
                *self.unsupported_legacy_records,
            ]
        }


def _row_value(row, key: str) -> str:
    try:
        return str(row[key] or '')
    except (KeyError, IndexError, TypeError):
        return ''


def _finding(row, reason: str) -> CleanupFinding:
    return CleanupFinding(
        document_id=int(row['id']),
        filename=_row_value(row, 'filename'),
        dropbox_path=_row_value(row, 'dropbox_path'),
        reason=reason,
    )


def _path_parts(path: str) -> list[str]:
    return [part for part in (path or '').replace('\\', '/').split('/') if part]


def _path_invalid_reason(path: str) -> str:
    if not path:
        return 'empty_dropbox_path'
    if '\x00' in path:
        return 'dropbox_path_contains_control_character'
    if not path.startswith('/'):
        return 'dropbox_path_must_start_with_slash'
    parts = _path_parts(path)
    if any(part in {'.', '..'} for part in parts):
        return 'dropbox_path_contains_traversal'
    if re.match(r'(?i)^[a-z]:', path):
        return 'dropbox_path_contains_drive_path'
    return ''


def _temporary_dev_path_reason(path: str) -> str:
    normalized_parts = {part.lower() for part in _path_parts(path)}
    if normalized_parts & TEMP_DEV_PATH_PARTS:
        return 'temporary_or_development_path'
    configured_base = (getattr(settings, 'dropbox_base_path', '') or '').rstrip('/')
    if configured_base and path and path.startswith('/') and not path.startswith(f'{configured_base}/'):
        return 'outside_configured_dropbox_base_path'
    return ''


def _ownership_failed(row) -> bool:
    path = _row_value(row, 'dropbox_path')
    if not path:
        return False
    expected_folder = safe_customer_folder(_row_value(row, 'customer_email'))
    stored_folder = _row_value(row, 'safe_customer_folder')
    parts = set(_path_parts(path))
    return bool(expected_folder and expected_folder not in parts and stored_folder and stored_folder not in parts)


def _is_testdata(row) -> bool:
    filename = _row_value(row, 'filename').lower()
    original_filename = _row_value(row, 'original_filename').lower()
    title = _row_value(row, 'title').lower()
    customer_email = _row_value(row, 'customer_email').lower()
    haystack = ' '.join([filename, original_filename, title, customer_email])
    if any(term in haystack for term in TESTDATA_FILENAME_TERMS):
        return True
    if customer_email.startswith(('test@', 'dummy@', 'sample@')):
        return True
    return False


def _approximate_reduction(total_records: int, candidate_ids: set[int]) -> int:
    database_path = settings.database_path
    if not total_records or not database_path.exists():
        return 0
    average_bytes = database_path.stat().st_size / total_records
    return int(average_bytes * len(candidate_ids))


def build_cleanup_report(*, check_dropbox: bool = True) -> CleanupReport:
    init_db()
    rows = all_documents()
    total_records = len(rows)
    path_counts = Counter(_row_value(row, 'dropbox_path') for row in rows if _row_value(row, 'dropbox_path'))

    orphaned_records: list[CleanupFinding] = []
    missing_dropbox_files: list[CleanupFinding] = []
    unsupported_legacy_records: list[CleanupFinding] = []
    temporary_dev_path_records: list[CleanupFinding] = []
    duplicate_records: list[CleanupFinding] = []
    ownership_failed_records: list[CleanupFinding] = []
    testdata_records: list[CleanupFinding] = []
    dropbox_errors: list[CleanupFinding] = []

    print(f"Cleanup report started | total_records={total_records} | check_dropbox={check_dropbox}")
    for row in rows:
        path = _row_value(row, 'dropbox_path')
        invalid_reason = _path_invalid_reason(path)
        if invalid_reason:
            orphaned_records.append(_finding(row, invalid_reason))
        else:
            temp_reason = _temporary_dev_path_reason(path)
            if temp_reason:
                temporary_dev_path_records.append(_finding(row, temp_reason))
            if _ownership_failed(row):
                ownership_failed_records.append(_finding(row, 'ownership_path_validation_failed'))
            if path_counts[path] > 1:
                duplicate_records.append(_finding(row, 'duplicate_dropbox_path'))
            if check_dropbox:
                try:
                    if not path_exists(path):
                        missing_dropbox_files.append(_finding(row, 'dropbox_file_missing'))
                except Exception as exc:
                    dropbox_errors.append(_finding(row, f'dropbox_check_error: {sanitize_for_log(exc)}'))

        extension = file_extension(_row_value(row, 'filename'))
        if extension in UNSUPPORTED_LEGACY_EXTENSIONS:
            unsupported_legacy_records.append(_finding(row, f'unsupported_legacy_extension:{extension}'))
        if _is_testdata(row):
            testdata_records.append(_finding(row, 'likely_test_or_development_record'))

    candidate_ids = {
        finding.document_id
        for finding in [
            *orphaned_records,
            *missing_dropbox_files,
            *unsupported_legacy_records,
            *temporary_dev_path_records,
            *ownership_failed_records,
            *testdata_records,
        ]
    }

    report = CleanupReport(
        total_records=total_records,
        orphaned_records=orphaned_records,
        missing_dropbox_files=missing_dropbox_files,
        unsupported_legacy_records=unsupported_legacy_records,
        temporary_dev_path_records=temporary_dev_path_records,
        duplicate_records=duplicate_records,
        ownership_failed_records=ownership_failed_records,
        testdata_records=testdata_records,
        dropbox_errors=dropbox_errors,
        approximate_db_reduction_bytes=_approximate_reduction(total_records, candidate_ids),
    )
    print_cleanup_report(report)
    return report


def print_cleanup_report(report: CleanupReport) -> None:
    print(
        "Cleanup report completed"
        f" | total_records={report.total_records}"
        f" | orphaned_records={len(report.orphaned_records)}"
        f" | missing_dropbox_files={len(report.missing_dropbox_files)}"
        f" | unsupported_legacy_records={len(report.unsupported_legacy_records)}"
        f" | temporary_dev_paths={len(report.temporary_dev_path_records)}"
        f" | duplicate_records={len(report.duplicate_records)}"
        f" | ownership_failed_records={len(report.ownership_failed_records)}"
        f" | testdata_records={len(report.testdata_records)}"
        f" | dropbox_errors={len(report.dropbox_errors)}"
        f" | approximate_db_reduction_bytes={report.approximate_db_reduction_bytes}"
    )
    for label, findings in (
        ('orphaned SQLite record', report.orphaned_records),
        ('missing Dropbox file', report.missing_dropbox_files),
        ('unsupported legacy record', report.unsupported_legacy_records),
        ('temporary/dev path record', report.temporary_dev_path_records),
        ('duplicate record', report.duplicate_records),
        ('ownership check failed', report.ownership_failed_records),
        ('likely test/dev record', report.testdata_records),
        ('Dropbox check error', report.dropbox_errors),
    ):
        for finding in findings:
            print(
                f"Cleanup finding: {label}"
                f" | document_id={finding.document_id}"
                f" | filename={sanitize_for_log(finding.filename)}"
                f" | reason={sanitize_for_log(finding.reason)}"
                f" | path={sanitize_for_log(finding.dropbox_path)}"
            )


def _delete_document_ids(document_ids: set[int]) -> int:
    if not document_ids:
        return 0
    placeholders = ','.join('?' for _ in document_ids)
    with closing(connect()) as conn:
        cursor = conn.execute(
            f'DELETE FROM documents WHERE id IN ({placeholders})',
            tuple(sorted(document_ids)),
        )
        deleted = cursor.rowcount
        conn.commit()
    return int(deleted or 0)


def cleanup_orphaned(*, confirm: bool = False) -> int:
    report = build_cleanup_report(check_dropbox=True)
    candidate_ids = report.orphaned_cleanup_ids
    print(
        "Cleanup orphaned summary"
        f" | candidate_rows={len(candidate_ids)}"
        f" | confirm={confirm}"
        f" | deletes_dropbox_files=false"
    )
    if not confirm:
        print("Dry-run only: no SQLite rows deleted.")
        return 0
    deleted = _delete_document_ids(candidate_ids)
    print(f"Cleanup orphaned completed | deleted_rows={deleted}")
    return deleted


def cleanup_testdata(*, confirm: bool = False) -> int:
    report = build_cleanup_report(check_dropbox=False)
    candidate_ids = report.testdata_cleanup_ids
    print(
        "Cleanup testdata summary"
        f" | candidate_rows={len(candidate_ids)}"
        f" | confirm={confirm}"
        f" | deletes_dropbox_files=false"
    )
    if not confirm:
        print("Dry-run only: no SQLite rows deleted.")
        return 0
    deleted = _delete_document_ids(candidate_ids)
    print(f"Cleanup testdata completed | deleted_rows={deleted}")
    return deleted


def _clear_logs() -> int:
    log_dir = settings.log_dir.resolve()
    deleted = 0
    if not log_dir.exists():
        return 0
    for path in log_dir.iterdir():
        resolved = path.resolve()
        if log_dir not in resolved.parents:
            raise RuntimeError(f'Refusing to delete outside log_dir: {sanitize_for_log(resolved)}')
        if path.is_file():
            path.unlink()
            deleted += 1
    return deleted


def reset_dev_environment(*, confirm: bool = False, clear_logs: bool = False) -> dict[str, int]:
    if not confirm:
        raise RuntimeError('reset-dev-environment requires --confirm')

    init_db()
    backup_path = create_backup(reason='pre-reset-dev-environment')
    with closing(connect()) as conn:
        document_count = int(conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0])
        rate_event_count = int(conn.execute('SELECT COUNT(*) FROM rate_limit_events').fetchone()[0])
        cooldown_count = int(conn.execute('SELECT COUNT(*) FROM rate_limit_cooldowns').fetchone()[0])
        conn.execute('DELETE FROM documents')
        conn.execute('DELETE FROM rate_limit_events')
        conn.execute('DELETE FROM rate_limit_cooldowns')
        conn.commit()

    deleted_logs = _clear_logs() if clear_logs else 0
    print(
        "Dev environment reset completed"
        f" | backup={sanitize_for_log(backup_path)}"
        f" | deleted_document_rows={document_count}"
        f" | deleted_rate_limit_events={rate_event_count}"
        f" | deleted_rate_limit_cooldowns={cooldown_count}"
        f" | deleted_log_files={deleted_logs}"
        f" | deletes_dropbox_files=false"
    )
    return {
        'documents': document_count,
        'rate_limit_events': rate_event_count,
        'rate_limit_cooldowns': cooldown_count,
        'logs': deleted_logs,
    }
