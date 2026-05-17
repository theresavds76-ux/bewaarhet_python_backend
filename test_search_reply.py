from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from bewaarhet.search_reply import send_search_results


def _row(filename: str, path: str) -> dict[str, str]:
    return {
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
            _row('missing.pdf', '/missing.pdf'),
            _row('found.pdf', '/found.pdf'),
        ]

        def temporary_link(path: str) -> str:
            if path == '/missing.pdf':
                raise Exception('not_found')
            return 'https://example.com/found'

        output = StringIO()
        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link', side_effect=temporary_link),
            patch('bewaarhet.search_reply.send_html') as send_html,
            redirect_stdout(output),
        ):
            send_search_results('user@example.com', 'factuur')

        self.assertIn('Dropbox path niet gevonden: /missing.pdf', output.getvalue())
        send_html.assert_called_once()
        subject = send_html.call_args.args[1]
        html = send_html.call_args.args[2]
        self.assertEqual(subject, 'Document(en) gevonden')
        self.assertIn('found.pdf', html)
        self.assertNotIn('missing.pdf', html)

    def test_sends_friendly_mail_when_all_matched_rows_are_missing(self) -> None:
        rows = [
            _row('missing-1.pdf', '/missing-1.pdf'),
            _row('missing-2.pdf', '/missing-2.pdf'),
        ]

        output = StringIO()
        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link', side_effect=Exception('not_found')),
            patch('bewaarhet.search_reply.send_html') as send_html,
            redirect_stdout(output),
        ):
            send_search_results('user@example.com', 'factuur')

        self.assertIn('Dropbox path niet gevonden: /missing-1.pdf', output.getvalue())
        self.assertIn('Dropbox path niet gevonden: /missing-2.pdf', output.getvalue())
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
