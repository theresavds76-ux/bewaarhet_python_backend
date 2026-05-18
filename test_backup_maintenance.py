from __future__ import annotations

import gc
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bewaarhet import backup, database, maintenance, worker


def _settings(root: Path, *, keep_latest: int = 14) -> SimpleNamespace:
    data_dir = root / 'portable data'
    settings = SimpleNamespace(
        data_dir=data_dir,
        database_path=data_dir / 'documents.db',
        backup_dir=data_dir / 'backups',
        log_dir=data_dir / 'logs',
        backup_keep_latest=keep_latest,
    )

    def ensure_directories() -> None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        settings.backup_dir.mkdir(parents=True, exist_ok=True)
        settings.log_dir.mkdir(parents=True, exist_ok=True)

    settings.ensure_directories = ensure_directories
    return settings


def _record(filename: str, path: str, *, customer: str = 'user@example.com') -> dict[str, str]:
    return {
        'customer_identity': customer,
        'customer_email': customer,
        'safe_customer_folder': customer.replace('@', '_at_'),
        'category': 'facturen',
        'filename': filename,
        'date_received': '2026-05-18',
        'dropbox_path': path,
        'original_filename': filename,
        'document_date': '2026-05-18',
        'domain': 'overig',
        'supplier': 'test',
        'purpose': 'factuur',
        'title': '',
        'ocr_preview': '',
        'ocr_text': '',
        'year': '2026',
        'month': '05',
    }


class BackupMaintenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings = _settings(Path(self.temp_dir.name), keep_latest=2)
        self.patchers = [
            patch('bewaarhet.database.settings', self.settings),
            patch('bewaarhet.backup.settings', self.settings),
            patch('bewaarhet.maintenance.init_db', database.init_db),
            patch('bewaarhet.worker.settings', self.settings),
        ]
        for patcher in self.patchers:
            patcher.start()
        database.init_db()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        gc.collect()
        self.temp_dir.cleanup()

    def test_backup_creation(self) -> None:
        database.add_document(_record('factuur.pdf', '/Bewaar het/Klanten/user/factuur.pdf'))

        backup_path = backup.create_backup(reason='manual-test')

        self.assertTrue(backup_path.exists())
        ok, message = backup.validate_database(backup_path)
        self.assertTrue(ok, message)

    def test_backup_rotation_keeps_latest_n(self) -> None:
        database.add_document(_record('factuur.pdf', '/Bewaar het/Klanten/user/factuur.pdf'))

        for index in range(4):
            backup.create_backup(reason=f'rotation-{index}', keep_latest=2)

        backups = backup.list_backups()
        self.assertEqual(len(backups), 2)

    def test_restore_validation_and_restore(self) -> None:
        database.add_document(_record('before.pdf', '/Bewaar het/Klanten/user/before.pdf'))
        backup_path = backup.create_backup(reason='restore-source')
        database.add_document(_record('after.pdf', '/Bewaar het/Klanten/user/after.pdf'))

        dry_run = backup.restore_backup(backup_path, dry_run=True)
        self.assertFalse(dry_run.restored)
        self.assertIn('no files changed', dry_run.message)

        backup.restore_backup(backup_path, confirm=True, backup_current=False)
        rows = database.all_documents()
        filenames = {row['filename'] for row in rows}
        self.assertEqual(filenames, {'before.pdf'})

        corrupt = self.settings.backup_dir / 'bewaarhet-corrupt.sqlite3'
        corrupt.write_text('not sqlite', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            backup.restore_backup(corrupt, dry_run=True)

    def test_path_portability_creates_nested_runtime_folders(self) -> None:
        self.settings.ensure_directories()

        self.assertTrue(self.settings.database_path.parent.exists())
        self.assertTrue(self.settings.backup_dir.exists())
        self.assertTrue(self.settings.log_dir.exists())
        self.assertNotIn('\\', self.settings.database_path.as_posix())

    def test_automatic_backup_before_schema_change(self) -> None:
        old_db = self.settings.database_path
        old_db.unlink()
        old_db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(old_db) as conn:
            conn.execute(
                '''
                CREATE TABLE documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_email TEXT NOT NULL,
                    safe_customer_folder TEXT NOT NULL,
                    category TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    date_received TEXT NOT NULL,
                    dropbox_path TEXT NOT NULL
                )
                '''
            )

        database.init_db()

        self.assertEqual(len(backup.list_backups()), 1)

    def test_consistency_check_reports_missing_orphaned_and_duplicates(self) -> None:
        database.add_document(_record('one.pdf', '/Bewaar het/Klanten/user/one.pdf'))
        database.add_document(_record('two.pdf', '/Bewaar het/Klanten/user/one.pdf', customer='other@example.com'))
        database.add_document(_record('orphan.pdf', '', customer='third@example.com'))

        with patch('bewaarhet.maintenance.path_exists', return_value=True):
            report = maintenance.run_dropbox_consistency_check()

        self.assertEqual(report.total_records, 3)
        self.assertEqual(report.duplicate_paths, {'/Bewaar het/Klanten/user/one.pdf': 2})
        self.assertEqual(report.orphaned_records, [3])

    def test_consistency_check_reports_missing_dropbox_file(self) -> None:
        database.add_document(_record('missing.pdf', '/Bewaar het/Klanten/user/missing.pdf'))

        with patch('bewaarhet.maintenance.path_exists', return_value=False):
            report = maintenance.run_dropbox_consistency_check()

        self.assertEqual(len(report.missing_files), 1)
        self.assertEqual(report.missing_files[0].filename, 'missing.pdf')

    def test_worker_startup_integrity_checks(self) -> None:
        output = StringIO()
        with (
            patch('bewaarhet.worker.init_db') as init_db,
            patch('bewaarhet.worker.check_integrity', return_value=(True, 'ok')) as check_integrity,
            redirect_stdout(output),
        ):
            worker.startup_diagnostics()

        init_db.assert_called_once()
        check_integrity.assert_called_once()
        self.assertIn('Bewaarhet worker startup diagnostics.', output.getvalue())
        self.assertIn('Database integrity check: ok', output.getvalue())


if __name__ == '__main__':
    unittest.main()
