from __future__ import annotations

import tempfile
import unittest
import gc
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bewaarhet import database


class DatabaseMissingFileTests(unittest.TestCase):
    def _add_document(self, **overrides) -> None:
        record = {
            'customer_email': 'user@example.com',
            'safe_customer_folder': 'user_example_com',
            'category': 'notities',
            'filename': 'notitie_wachtwoord_aaa_17-05-2026.pdf',
            'date_received': '2026-05-17',
            'dropbox_path': '/Bewaar het/Klanten/user/notities/notitie_wachtwoord_aaa_17-05-2026.pdf',
            'domain': 'overig',
            'purpose': 'notitie',
            'ocr_preview': 'Wachtwoord voor AAA',
            'ocr_text': 'Wachtwoord voor AAA is AAEUUUE',
            'year': '2026',
            'month': '05',
        }
        record.update(overrides)
        database.add_document(record)

    def test_missing_file_records_are_excluded_from_searches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = SimpleNamespace(database_path=Path(tmp) / 'bewaarhet.sqlite3')
            with patch('bewaarhet.database.settings', settings):
                database.init_db()
                database.add_document({
                    'customer_email': 'user@example.com',
                    'safe_customer_folder': 'user_example_com',
                    'category': 'facturen',
                    'filename': 'factuur_test_17-05-2026.pdf',
                    'date_received': '2026-05-17',
                    'dropbox_path': '/missing.pdf',
                    'domain': 'overig',
                    'ocr_preview': 'test factuur',
                    'ocr_text': 'test factuur',
                    'year': '2026',
                    'month': '05',
                })

                self.assertEqual(len(database.search_documents('user@example.com', 'factuur')), 1)
                document_id = database.all_documents()[0]['id']
                database.mark_missing_file(document_id)
                self.assertEqual(database.search_documents('user@example.com', 'factuur'), [])
            gc.collect()

    def test_search_normalizes_ww_alias_for_stored_note_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = SimpleNamespace(database_path=Path(tmp) / 'bewaarhet.sqlite3')
            with patch('bewaarhet.database.settings', settings):
                database.init_db()
                self._add_document()

                rows = database.search_documents('user@example.com', 'ww AAA')

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['filename'], 'notitie_wachtwoord_aaa_17-05-2026.pdf')
            gc.collect()

    def test_search_includes_dropbox_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = SimpleNamespace(database_path=Path(tmp) / 'bewaarhet.sqlite3')
            with patch('bewaarhet.database.settings', settings):
                database.init_db()
                self._add_document(
                    filename='document_17-05-2026.pdf',
                    ocr_preview='',
                    ocr_text='',
                    dropbox_path='/Bewaar het/Klanten/user/notities/notitie_sleutel_17-05-2026.pdf',
                )

                rows = database.search_documents('user@example.com', 'sleutel')

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['dropbox_path'], '/Bewaar het/Klanten/user/notities/notitie_sleutel_17-05-2026.pdf')
            gc.collect()


if __name__ == '__main__':
    unittest.main()
