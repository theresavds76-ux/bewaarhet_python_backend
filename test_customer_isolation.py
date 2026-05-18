from __future__ import annotations

import gc
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bewaarhet import database
from bewaarhet.search_reply import send_search_results


def _record(
    customer_email: str,
    safe_customer_folder: str,
    filename: str,
    text: str,
    *,
    dropbox_path: str | None = None,
) -> dict[str, str]:
    return {
        'customer_email': customer_email,
        'customer_identity': customer_email.lower(),
        'safe_customer_folder': safe_customer_folder,
        'category': 'facturen',
        'filename': filename,
        'date_received': '2026-05-17',
        'dropbox_path': dropbox_path or f'/Bewaar het/Klanten/{safe_customer_folder}/facturen/{filename}',
        'domain': 'overig',
        'purpose': 'factuur',
        'ocr_preview': text,
        'ocr_text': text,
        'year': '2026',
        'month': '05',
    }


def _row(
    customer_email: str,
    safe_customer_folder: str,
    filename: str,
    path: str,
    document_id: int = 1,
) -> dict[str, str | int]:
    return {
        'id': document_id,
        'customer_identity': customer_email.lower(),
        'customer_email': customer_email,
        'safe_customer_folder': safe_customer_folder,
        'filename': filename,
        'supplier': '',
        'purpose': 'factuur',
        'title': '',
        'original_filename': '',
        'category': 'facturen',
        'domain': 'overig',
        'ocr_preview': 'isolatie factuur',
        'ocr_text': 'isolatie factuur',
        'year': '2026',
        'month': '05',
        'date_received': '2026-05-17',
        'dropbox_path': path,
    }


class CustomerIsolationTests(unittest.TestCase):
    def test_user_a_cannot_retrieve_user_b_document(self) -> None:
        rows = [
            _row(
                'userb@example.com',
                'userb_at_example.com',
                'factuur_user_b_17-05-2026.pdf',
                '/Bewaar het/Klanten/userb_at_example.com/facturen/factuur_user_b_17-05-2026.pdf',
            )
        ]

        output = StringIO()
        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link') as temporary_link,
            patch('bewaarhet.search_reply.send_html') as send_html,
            redirect_stdout(output),
        ):
            send_search_results('usera@example.com', 'isolatie factuur')

        temporary_link.assert_not_called()
        send_html.assert_called_once()
        self.assertEqual(send_html.call_args.args[1], 'Geen passend document gevonden')
        self.assertIn('ownership check failed', output.getvalue())

    def test_same_user_can_retrieve_own_document(self) -> None:
        rows = [
            _row(
                'usera@example.com',
                'usera_at_example.com',
                'factuur_user_a_17-05-2026.pdf',
                '/Bewaar het/Klanten/usera_at_example.com/facturen/factuur_user_a_17-05-2026.pdf',
            )
        ]

        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link', return_value='https://example.com/doc') as temporary_link,
            patch('bewaarhet.search_reply.send_html') as send_html,
        ):
            send_search_results('usera@example.com', 'isolatie factuur')

        temporary_link.assert_called_once_with('/Bewaar het/Klanten/usera_at_example.com/facturen/factuur_user_a_17-05-2026.pdf')
        self.assertEqual(send_html.call_args.args[1], 'Document(en) gevonden')
        self.assertIn('factuur_user_a_17-05-2026.pdf', send_html.call_args.args[2])

    def test_similar_domains_do_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = SimpleNamespace(database_path=Path(tmp) / 'bewaarhet.sqlite3')
            with patch('bewaarhet.database.settings', settings):
                database.init_db()
                database.add_document(_record(
                    'user@example.co',
                    'user_at_example.co',
                    'factuur_andere_domein_17-05-2026.pdf',
                    'alleenbijanderedomein factuur',
                ))

                rows = database.search_documents('user@example.com', 'alleenbijanderedomein')

                self.assertEqual(rows, [])
            gc.collect()

    def test_path_traversal_attempt_does_not_bypass_ownership(self) -> None:
        rows = [
            _row(
                'userb@example.com',
                'userb_at_example.com',
                'factuur_user_b_17-05-2026.pdf',
                '/Bewaar het/Klanten/usera_at_example.com/../userb_at_example.com/facturen/factuur_user_b_17-05-2026.pdf',
            )
        ]

        output = StringIO()
        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link') as temporary_link,
            patch('bewaarhet.search_reply.send_html') as send_html,
            redirect_stdout(output),
        ):
            send_search_results('usera@example.com', 'isolatie factuur')

        temporary_link.assert_not_called()
        self.assertEqual(send_html.call_args.args[1], 'Geen passend document gevonden')
        self.assertIn('ownership check failed', output.getvalue())

    def test_search_query_cannot_force_global_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = SimpleNamespace(database_path=Path(tmp) / 'bewaarhet.sqlite3')
            with patch('bewaarhet.database.settings', settings):
                database.init_db()
                database.add_document(_record(
                    'usera@example.com',
                    'usera_at_example.com',
                    'factuur_user_a_17-05-2026.pdf',
                    'eigen document factuur',
                ))
                database.add_document(_record(
                    'userb@example.com',
                    'userb_at_example.com',
                    'factuur_user_b_17-05-2026.pdf',
                    'secretglobal factuur',
                ))

                rows = database.search_documents('usera@example.com', "secretglobal' OR 1=1 --")

                self.assertEqual(rows, [])
            gc.collect()


if __name__ == '__main__':
    unittest.main()
