from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .database import all_documents, init_db
from .dropbox_client import path_exists
from .utils import sanitize_for_log


@dataclass(frozen=True)
class MissingDropboxFile:
    document_id: int
    filename: str
    dropbox_path: str


@dataclass(frozen=True)
class DropboxCheckReport:
    total_records: int = 0
    checked_paths: int = 0
    missing_files: list[MissingDropboxFile] = field(default_factory=list)
    orphaned_records: list[int] = field(default_factory=list)
    duplicate_paths: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def has_findings(self) -> bool:
        return bool(self.missing_files or self.orphaned_records or self.duplicate_paths or self.errors)


def run_dropbox_consistency_check() -> DropboxCheckReport:
    init_db()
    rows = all_documents()
    paths = [(int(row['id']), row['filename'], row['dropbox_path']) for row in rows]

    orphaned_records = [document_id for document_id, _filename, path in paths if not path]
    path_counts = Counter(path for _document_id, _filename, path in paths if path)
    duplicate_paths = {path: count for path, count in path_counts.items() if count > 1}

    missing_files: list[MissingDropboxFile] = []
    errors: dict[str, str] = {}
    checked_paths = 0
    for document_id, filename, dropbox_path in paths:
        if not dropbox_path:
            continue
        checked_paths += 1
        try:
            if not path_exists(dropbox_path):
                missing_files.append(MissingDropboxFile(document_id, filename, dropbox_path))
        except Exception as exc:
            errors[dropbox_path] = sanitize_for_log(exc)

    report = DropboxCheckReport(
        total_records=len(rows),
        checked_paths=checked_paths,
        missing_files=missing_files,
        orphaned_records=orphaned_records,
        duplicate_paths=duplicate_paths,
        errors=errors,
    )
    print_consistency_report(report)
    return report


def print_consistency_report(report: DropboxCheckReport) -> None:
    print(
        "Dropbox consistency check completed"
        f" | total_records={report.total_records}"
        f" | checked_paths={report.checked_paths}"
        f" | missing_files={len(report.missing_files)}"
        f" | orphaned_records={len(report.orphaned_records)}"
        f" | duplicate_paths={len(report.duplicate_paths)}"
        f" | errors={len(report.errors)}"
    )
    for item in report.missing_files:
        print(
            "Dropbox file missing"
            f" | document_id={item.document_id}"
            f" | filename={sanitize_for_log(item.filename)}"
            f" | path={sanitize_for_log(item.dropbox_path)}"
        )
    for document_id in report.orphaned_records:
        print(f"Orphaned record | document_id={document_id} | reason=empty_dropbox_path")
    for path, count in report.duplicate_paths.items():
        print(f"Duplicate Dropbox path | path={sanitize_for_log(path)} | count={count}")
    for path, error in report.errors.items():
        print(f"Dropbox check error | path={sanitize_for_log(path)} | error={sanitize_for_log(error)}")
