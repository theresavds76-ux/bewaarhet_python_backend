from __future__ import annotations

import socket
import time
from collections import Counter
from dataclasses import dataclass, field

from .config import settings
from .database import documents_for_consistency_check, init_db
from .dropbox_client import path_exists
from .utils import sanitize_for_log

try:
    import requests
except Exception:  # pragma: no cover - defensive for minimal installs
    requests = None  # type: ignore[assignment]


@dataclass(frozen=True)
class MissingDropboxFile:
    document_id: int
    filename: str
    dropbox_path: str


@dataclass(frozen=True)
class DropboxCheckError:
    document_id: int
    filename: str
    dropbox_path: str
    message: str
    duration_seconds: float


@dataclass(frozen=True)
class InvalidDropboxPath:
    document_id: int
    filename: str
    dropbox_path: str
    reason: str


@dataclass(frozen=True)
class SlowDropboxCheck:
    document_id: int
    filename: str
    dropbox_path: str
    duration_seconds: float


@dataclass(frozen=True)
class DropboxCheckReport:
    total_records: int = 0
    checked_paths: int = 0
    missing_files: list[MissingDropboxFile] = field(default_factory=list)
    orphaned_records: list[int] = field(default_factory=list)
    duplicate_paths: dict[str, int] = field(default_factory=dict)
    invalid_paths: list[InvalidDropboxPath] = field(default_factory=list)
    timeout_errors: list[DropboxCheckError] = field(default_factory=list)
    api_errors: list[DropboxCheckError] = field(default_factory=list)
    slow_records: list[SlowDropboxCheck] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    average_seconds_per_record: float = 0.0

    @property
    def errors(self) -> dict[str, str]:
        return {error.dropbox_path: error.message for error in [*self.timeout_errors, *self.api_errors]}

    @property
    def has_findings(self) -> bool:
        return bool(
            self.missing_files
            or self.orphaned_records
            or self.duplicate_paths
            or self.invalid_paths
            or self.timeout_errors
            or self.api_errors
        )


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    if requests is not None and isinstance(exc, requests.exceptions.Timeout):
        return True
    name = exc.__class__.__name__.lower()
    return 'timeout' in name or 'timed out' in str(exc).lower()


def _invalid_path_reason(path: str) -> str:
    if not path:
        return 'empty_dropbox_path'
    if not path.startswith('/'):
        return 'dropbox_path_must_start_with_slash'
    if '\x00' in path:
        return 'dropbox_path_contains_control_character'
    return ''


def _log_progress(index: int, total: int, row) -> None:
    print(
        "Dropbox consistency progress"
        f" | record={index}/{total}"
        f" | document_id={int(row['id'])}"
        f" | filename={sanitize_for_log(row['filename'])}"
        f" | category={sanitize_for_log(row['category'])}"
        f" | path={sanitize_for_log(row['dropbox_path'])}"
    )


def run_dropbox_consistency_check(
    *,
    limit: int | None = None,
    since_id: int | None = None,
    log_every: int | None = None,
    slow_threshold_seconds: float | None = None,
) -> DropboxCheckReport:
    init_db()
    rows = documents_for_consistency_check(limit=limit, since_id=since_id)
    total_records = len(rows)
    progress_interval = max(1, log_every or getattr(settings, 'consistency_log_every', 10))
    slow_threshold = (
        getattr(settings, 'consistency_slow_threshold_seconds', 2.0)
        if slow_threshold_seconds is None
        else slow_threshold_seconds
    )

    print(
        "Dropbox consistency check started"
        f" | total_records={total_records}"
        f" | limit={limit if limit is not None else 'none'}"
        f" | since_id={since_id if since_id is not None else 'none'}"
        f" | log_every={progress_interval}"
        f" | slow_threshold={slow_threshold:.3f}s"
    )

    path_counts = Counter(row['dropbox_path'] for row in rows if row['dropbox_path'])
    duplicate_paths = {path: count for path, count in path_counts.items() if count > 1}

    missing_files: list[MissingDropboxFile] = []
    orphaned_records: list[int] = []
    invalid_paths: list[InvalidDropboxPath] = []
    timeout_errors: list[DropboxCheckError] = []
    api_errors: list[DropboxCheckError] = []
    slow_records: list[SlowDropboxCheck] = []

    checked_paths = 0
    started = time.perf_counter()
    for index, row in enumerate(rows, start=1):
        if index == 1 or index == total_records or index % progress_interval == 0:
            _log_progress(index, total_records, row)

        document_id = int(row['id'])
        filename = row['filename']
        dropbox_path = row['dropbox_path'] or ''
        invalid_reason = _invalid_path_reason(dropbox_path)
        if invalid_reason:
            if invalid_reason == 'empty_dropbox_path':
                orphaned_records.append(document_id)
            else:
                invalid_paths.append(InvalidDropboxPath(document_id, filename, dropbox_path, invalid_reason))
            print(
                "Dropbox path invalid"
                f" | document_id={document_id}"
                f" | filename={sanitize_for_log(filename)}"
                f" | reason={sanitize_for_log(invalid_reason)}"
                f" | path={sanitize_for_log(dropbox_path)}"
            )
            continue

        record_started = time.perf_counter()
        checked_paths += 1
        try:
            exists = path_exists(dropbox_path)
            duration = time.perf_counter() - record_started
            if duration > slow_threshold:
                slow = SlowDropboxCheck(document_id, filename, dropbox_path, duration)
                slow_records.append(slow)
                print(
                    "Slow Dropbox metadata check"
                    f" | document_id={document_id}"
                    f" | filename={sanitize_for_log(filename)}"
                    f" | duration={duration:.3f}s"
                    f" | path={sanitize_for_log(dropbox_path)}"
                )
            if not exists:
                missing_files.append(MissingDropboxFile(document_id, filename, dropbox_path))
                print(
                    "Dropbox file missing"
                    f" | document_id={document_id}"
                    f" | filename={sanitize_for_log(filename)}"
                    f" | duration={duration:.3f}s"
                    f" | path={sanitize_for_log(dropbox_path)}"
                )
        except Exception as exc:
            duration = time.perf_counter() - record_started
            error = DropboxCheckError(document_id, filename, dropbox_path, sanitize_for_log(exc), duration)
            if _is_timeout_error(exc):
                timeout_errors.append(error)
                print(
                    "Dropbox metadata check timeout"
                    f" | document_id={document_id}"
                    f" | filename={sanitize_for_log(filename)}"
                    f" | duration={duration:.3f}s"
                    f" | path={sanitize_for_log(dropbox_path)}"
                    f" | error={sanitize_for_log(exc)}"
                )
            else:
                api_errors.append(error)
                print(
                    "Dropbox metadata check error"
                    f" | document_id={document_id}"
                    f" | filename={sanitize_for_log(filename)}"
                    f" | duration={duration:.3f}s"
                    f" | path={sanitize_for_log(dropbox_path)}"
                    f" | error={sanitize_for_log(exc)}"
                )

    total_duration = time.perf_counter() - started
    average = total_duration / total_records if total_records else 0.0
    slow_records = sorted(slow_records, key=lambda item: item.duration_seconds, reverse=True)[:10]

    report = DropboxCheckReport(
        total_records=total_records,
        checked_paths=checked_paths,
        missing_files=missing_files,
        orphaned_records=orphaned_records,
        duplicate_paths=duplicate_paths,
        invalid_paths=invalid_paths,
        timeout_errors=timeout_errors,
        api_errors=api_errors,
        slow_records=slow_records,
        total_duration_seconds=total_duration,
        average_seconds_per_record=average,
    )
    print_consistency_report(report)
    return report


def print_consistency_report(report: DropboxCheckReport) -> None:
    error_count = len(report.timeout_errors) + len(report.api_errors)
    print(
        "Dropbox consistency check completed"
        f" | checked_count={report.checked_paths}"
        f" | total_records={report.total_records}"
        f" | missing_count={len(report.missing_files)}"
        f" | error_count={error_count}"
        f" | timeout_count={len(report.timeout_errors)}"
        f" | invalid_path_count={len(report.invalid_paths)}"
        f" | orphaned_records={len(report.orphaned_records)}"
        f" | duplicate_paths={len(report.duplicate_paths)}"
        f" | duration_total={report.total_duration_seconds:.3f}s"
        f" | average_per_record={report.average_seconds_per_record:.3f}s"
    )
    for document_id in report.orphaned_records:
        print(f"Orphaned record | document_id={document_id} | reason=empty_dropbox_path")
    for item in report.invalid_paths:
        print(
            "Invalid Dropbox path"
            f" | document_id={item.document_id}"
            f" | filename={sanitize_for_log(item.filename)}"
            f" | reason={sanitize_for_log(item.reason)}"
            f" | path={sanitize_for_log(item.dropbox_path)}"
        )
    for path, count in report.duplicate_paths.items():
        print(f"Duplicate Dropbox path | path={sanitize_for_log(path)} | count={count}")
    for error in report.timeout_errors:
        print(
            "Dropbox timeout summary"
            f" | document_id={error.document_id}"
            f" | filename={sanitize_for_log(error.filename)}"
            f" | duration={error.duration_seconds:.3f}s"
            f" | path={sanitize_for_log(error.dropbox_path)}"
            f" | error={sanitize_for_log(error.message)}"
        )
    for error in report.api_errors:
        print(
            "Dropbox API error summary"
            f" | document_id={error.document_id}"
            f" | filename={sanitize_for_log(error.filename)}"
            f" | duration={error.duration_seconds:.3f}s"
            f" | path={sanitize_for_log(error.dropbox_path)}"
            f" | error={sanitize_for_log(error.message)}"
        )
    for item in report.slow_records:
        print(
            "Slowest Dropbox check"
            f" | document_id={item.document_id}"
            f" | filename={sanitize_for_log(item.filename)}"
            f" | duration={item.duration_seconds:.3f}s"
            f" | path={sanitize_for_log(item.dropbox_path)}"
        )
