from __future__ import annotations

import tempfile
import unittest
import gc
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bewaarhet import database


class DatabaseMissingFileTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
