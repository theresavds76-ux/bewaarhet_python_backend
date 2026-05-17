from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from bewaarhet.search_reply import send_search_results


def _row(filename: str, path: str, document_id: int = 1) -> dict[str, str | int]:
    return {
        'id': document_id,
        'filename': filename,
        'category': 'facturen',
        'domain': 'overig',
        'ocr_preview': '',
        'ocr_text': '',
        'year': '2026',
        'month': '05',
        'date_received': '2026-05-17',
        'dropbox_path': path,
    }


class SearchReplyTests(unittest.TestCase):
    def test_skips_missing_dropbox_path_and_sends_remaining_results(self) -> None:
        rows = [
            _row('missing.pdf', '/missing.pdf', 1),
            _row('found.pdf', '/found.pdf', 2),
        ]

        def temporary_link(path: str) -> str:
            if path == '/missing.pdf':
                raise Exception('not_found')
            return 'https://example.com/found'

        output = StringIO()
        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link', side_effect=temporary_link),
            patch('bewaarhet.search_reply.mark_missing_file') as mark_missing_file,
            patch('bewaarhet.search_reply.send_html') as send_html,
            redirect_stdout(output),
        ):
            send_search_results('user@example.com', 'factuur')

        self.assertIn('Dropbox path niet gevonden: /missing.pdf', output.getvalue())
        mark_missing_file.assert_called_once_with(1)
        send_html.assert_called_once()
        subject = send_html.call_args.args[1]
        html = send_html.call_args.args[2]
        self.assertEqual(subject, 'Document(en) gevonden')
        self.assertIn('found.pdf', html)
        self.assertNotIn('missing.pdf', html)

    def test_sends_friendly_mail_when_all_matched_rows_are_missing(self) -> None:
        rows = [
            _row('missing-1.pdf', '/missing-1.pdf', 1),
            _row('missing-2.pdf', '/missing-2.pdf', 2),
        ]

        output = StringIO()
        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link', side_effect=Exception('not_found')),
            patch('bewaarhet.search_reply.mark_missing_file') as mark_missing_file,
            patch('bewaarhet.search_reply.send_html') as send_html,
            redirect_stdout(output),
        ):
            send_search_results('user@example.com', 'factuur')

        self.assertIn('Dropbox path niet gevonden: /missing-1.pdf', output.getvalue())
        self.assertIn('Dropbox path niet gevonden: /missing-2.pdf', output.getvalue())
        self.assertEqual([call.args[0] for call in mark_missing_file.call_args_list], [1, 2])
        send_html.assert_called_once()
        subject = send_html.call_args.args[1]
        html = send_html.call_args.args[2]
        self.assertEqual(subject, 'Bestand niet meer gevonden')
        self.assertIn(
            'Ik vond wel gegevens die lijken te passen, maar het bestand zelf kon niet meer in Dropbox worden gevonden.',
            html,
        )


if __name__ == '__main__':
    unittest.main()
