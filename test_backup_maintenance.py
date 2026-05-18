from __future__ import annotations

import gc
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bewaarhet import backup, cleanup, database, maintenance, worker


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
            patch('bewaarhet.cleanup.settings', self.settings),
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

    def test_consistency_check_supports_limit_and_since_id(self) -> None:
        database.add_document(_record('one.pdf', '/Bewaar het/Klanten/user/one.pdf'))
        database.add_document(_record('two.pdf', '/Bewaar het/Klanten/user/two.pdf', customer='two@example.com'))
        database.add_document(_record('three.pdf', '/Bewaar het/Klanten/user/three.pdf', customer='three@example.com'))

        with patch('bewaarhet.maintenance.path_exists', return_value=True) as path_exists:
            report = maintenance.run_dropbox_consistency_check(limit=1, since_id=1, log_every=1)

        self.assertEqual(report.total_records, 1)
        self.assertEqual(report.checked_paths, 1)
        path_exists.assert_called_once_with('/Bewaar het/Klanten/user/two.pdf')

    def test_consistency_check_reports_missing_dropbox_file(self) -> None:
        database.add_document(_record('missing.pdf', '/Bewaar het/Klanten/user/missing.pdf'))

        with patch('bewaarhet.maintenance.path_exists', return_value=False):
            report = maintenance.run_dropbox_consistency_check()

        self.assertEqual(len(report.missing_files), 1)
        self.assertEqual(report.missing_files[0].filename, 'missing.pdf')

    def test_consistency_check_continues_after_timeout_and_api_errors(self) -> None:
        database.add_document(_record('timeout.pdf', '/Bewaar het/Klanten/user/timeout.pdf'))
        database.add_document(_record('api.pdf', '/Bewaar het/Klanten/user/api.pdf', customer='api@example.com'))
        database.add_document(_record('ok.pdf', '/Bewaar het/Klanten/user/ok.pdf', customer='ok@example.com'))

        with patch(
            'bewaarhet.maintenance.path_exists',
            side_effect=[TimeoutError('timed out'), RuntimeError('api unavailable'), True],
        ) as path_exists:
            report = maintenance.run_dropbox_consistency_check(log_every=1)

        self.assertEqual(path_exists.call_count, 3)
        self.assertEqual(len(report.timeout_errors), 1)
        self.assertEqual(len(report.api_errors), 1)
        self.assertEqual(report.checked_paths, 3)

    def test_consistency_check_reports_invalid_paths_without_dropbox_call(self) -> None:
        database.add_document(_record('invalid.pdf', 'relative/path.pdf'))

        with patch('bewaarhet.maintenance.path_exists') as path_exists:
            report = maintenance.run_dropbox_consistency_check()

        path_exists.assert_not_called()
        self.assertEqual(len(report.invalid_paths), 1)
        self.assertEqual(report.invalid_paths[0].reason, 'dropbox_path_must_start_with_slash')

    def test_consistency_check_logs_progress_and_slow_records(self) -> None:
        database.add_document(_record('slow.pdf', '/Bewaar het/Klanten/user/slow.pdf'))
        output = StringIO()

        with (
            patch('bewaarhet.maintenance.path_exists', return_value=True),
            patch('bewaarhet.maintenance.time.perf_counter', side_effect=[0.0, 0.1, 2.6, 2.7]),
            redirect_stdout(output),
        ):
            report = maintenance.run_dropbox_consistency_check(log_every=1, slow_threshold_seconds=1.0)

        self.assertEqual(len(report.slow_records), 1)
        self.assertIn('Dropbox consistency check started', output.getvalue())
        self.assertIn('Dropbox consistency progress | record=1/1', output.getvalue())
        self.assertIn('Slow Dropbox metadata check', output.getvalue())
        self.assertIn('average_per_record=', output.getvalue())

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

    def test_cleanup_orphaned_dry_run_does_not_delete(self) -> None:
        database.add_document(_record('missing.pdf', '/Bewaar het/Klanten/user/missing.pdf'))

        with patch('bewaarhet.cleanup.path_exists', return_value=False):
            deleted = cleanup.cleanup_orphaned(confirm=False)

        self.assertEqual(deleted, 0)
        self.assertEqual(len(database.all_documents()), 1)

    def test_cleanup_report_detects_orphans_and_duplicates(self) -> None:
        database.add_document(_record('one.pdf', '/Bewaar het/Klanten/user/one.pdf'))
        database.add_document(_record('two.pdf', '/Bewaar het/Klanten/user/one.pdf', customer='other@example.com'))
        database.add_document(_record('orphan.pdf', '', customer='third@example.com'))

        with patch('bewaarhet.cleanup.path_exists', return_value=True):
            report = cleanup.build_cleanup_report()

        self.assertEqual(len(report.orphaned_records), 1)
        self.assertEqual(len(report.duplicate_records), 2)

    def test_cleanup_testdata_detection_and_confirm_delete(self) -> None:
        database.add_document(_record('testje.pdf', '/Bewaar het/Klanten/user/testje.pdf'))
        database.add_document(_record('legacy.webp', '/Bewaar het/Klanten/user/legacy.webp', customer='legacy@example.com'))
        database.add_document(_record('invoice.pdf', '/Bewaar het/Klanten/user/invoice.pdf', customer='real@example.com'))

        dry_run = cleanup.cleanup_testdata(confirm=False)
        self.assertEqual(dry_run, 0)
        self.assertEqual(len(database.all_documents()), 3)

        deleted = cleanup.cleanup_testdata(confirm=True)
        self.assertEqual(deleted, 2)
        filenames = {row['filename'] for row in database.all_documents()}
        self.assertEqual(filenames, {'invoice.pdf'})

    def test_reset_dev_environment_requires_confirmation(self) -> None:
        with self.assertRaises(RuntimeError):
            cleanup.reset_dev_environment(confirm=False)

    def test_reset_dev_environment_backs_up_before_clearing_metadata(self) -> None:
        database.add_document(_record('invoice.pdf', '/Bewaar het/Klanten/user/invoice.pdf'))
        with closing(database.connect()) as conn:
            conn.execute(
                "INSERT INTO rate_limit_events (sender, action, created_at) VALUES (?, ?, ?)",
                ('user@example.com', 'search', 1000),
            )
            conn.execute(
                "INSERT INTO rate_limit_cooldowns (sender, action, cooldown_start, cooldown_until) VALUES (?, ?, ?, ?)",
                ('user@example.com', 'search', 1000, 4600),
            )
            conn.commit()

        with patch('bewaarhet.cleanup.create_backup', return_value=self.settings.backup_dir / 'backup.sqlite3') as create_backup:
            result = cleanup.reset_dev_environment(confirm=True)

        create_backup.assert_called_once_with(reason='pre-reset-dev-environment')
        self.assertEqual(result['documents'], 1)
        self.assertEqual(result['rate_limit_events'], 1)
        self.assertEqual(result['rate_limit_cooldowns'], 1)
        self.assertEqual(len(database.all_documents()), 0)
        with closing(database.connect()) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM rate_limit_events').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM rate_limit_cooldowns').fetchone()[0], 0)

    def test_reset_log_cleanup_stays_inside_configured_log_dir(self) -> None:
        self.settings.log_dir.mkdir(parents=True, exist_ok=True)
        inside_log = self.settings.log_dir / 'worker.log'
        inside_log.write_text('safe to clear', encoding='utf-8')
        outside_file = Path(self.temp_dir.name) / 'keep.log'
        outside_file.write_text('do not touch', encoding='utf-8')

        with patch('bewaarhet.cleanup.create_backup', return_value=self.settings.backup_dir / 'backup.sqlite3'):
            result = cleanup.reset_dev_environment(confirm=True, clear_logs=True)

        self.assertEqual(result['logs'], 1)
        self.assertFalse(inside_log.exists())
        self.assertTrue(outside_file.exists())


if __name__ == '__main__':
    unittest.main()
