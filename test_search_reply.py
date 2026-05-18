from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from bewaarhet.search_reply import send_search_results


def _row(
    filename: str,
    path: str,
    document_id: int = 1,
    *,
    supplier: str = '',
    purpose: str = 'factuur',
    category: str = 'facturen',
    domain: str = 'overig',
    ocr_preview: str = '',
    ocr_text: str = '',
) -> dict[str, str | int]:
    return {
        'id': document_id,
        'filename': filename,
        'supplier': supplier,
        'purpose': purpose,
        'title': '',
        'original_filename': '',
        'category': category,
        'domain': domain,
        'ocr_preview': ocr_preview,
        'ocr_text': ocr_text,
        'year': '2026',
        'month': '05',
        'date_received': '2026-05-17',
        'dropbox_path': path,
    }


class SearchReplyTests(unittest.TestCase):
    def test_skips_missing_dropbox_path_and_sends_remaining_results(self) -> None:
        rows = [
            _row('factuur_missing.pdf', '/missing.pdf', 1),
            _row('factuur_found.pdf', '/found.pdf', 2),
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
        self.assertIn('Search reply generation started | recipient=user@example.com | relevant_count=2', output.getvalue())
        self.assertIn(
            'Preparing search reply attachments/links | recipient=user@example.com | link_candidates=2 | attachment_count=0',
            output.getvalue(),
        )
        self.assertIn('Attachment preparation duration | recipient=user@example.com | attachment_count=0 | duration=', output.getvalue())
        self.assertIn('Dropbox link generation duration | recipient=user@example.com | generated_links=1 | duration=', output.getvalue())
        mark_missing_file.assert_called_once_with(1)
        send_html.assert_called_once()
        subject = send_html.call_args.args[1]
        html = send_html.call_args.args[2]
        self.assertEqual(subject, 'Document(en) gevonden')
        self.assertIn('factuur_found.pdf', html)
        self.assertNotIn('factuur_missing.pdf', html)

    def test_sends_friendly_mail_when_all_matched_rows_are_missing(self) -> None:
        rows = [
            _row('factuur_missing-1.pdf', '/missing-1.pdf', 1),
            _row('factuur_missing-2.pdf', '/missing-2.pdf', 2),
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

    def test_polis_lemonade_returns_only_relevant_result(self) -> None:
        rows = [
            _row('polis_lemonade_17-05-2026.pdf', '/polis.pdf', 1, supplier='lemonade', purpose='polis'),
            _row('factuur_infomedics_17-05-2026.pdf', '/infomedics.pdf', 2, supplier='infomedics', purpose='factuur'),
        ]

        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link', return_value='https://example.com/document') as temporary_link,
            patch('bewaarhet.search_reply.send_html') as send_html,
        ):
            send_search_results('user@example.com', 'polis lemonade')

        temporary_link.assert_called_once_with('/polis.pdf')
        send_html.assert_called_once()
        html = send_html.call_args.args[2]
        self.assertIn('polis_lemonade_17-05-2026.pdf', html)
        self.assertNotIn('factuur_infomedics_17-05-2026.pdf', html)

    def test_unrelated_zero_score_result_is_excluded(self) -> None:
        rows = [
            _row('factuur_infomedics_17-05-2026.pdf', '/infomedics.pdf', 1, supplier='infomedics', purpose='factuur'),
        ]

        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link') as temporary_link,
            patch('bewaarhet.search_reply.send_html') as send_html,
        ):
            send_search_results('user@example.com', 'polis lemonade')

        temporary_link.assert_not_called()
        send_html.assert_called_once()
        self.assertEqual(send_html.call_args.args[1], 'Geen passend document gevonden')

    def test_weak_match_below_thirty_is_excluded(self) -> None:
        rows = [
            _row('random_document.pdf', '/random.pdf', 1, purpose='factuur', category='overig'),
        ]

        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link') as temporary_link,
            patch('bewaarhet.search_reply.send_html') as send_html,
        ):
            send_search_results('user@example.com', 'factuur')

        temporary_link.assert_not_called()
        send_html.assert_called_once()
        self.assertEqual(send_html.call_args.args[1], 'Geen passend document gevonden')

    def test_result_list_is_not_padded_with_irrelevant_rows(self) -> None:
        rows = [
            _row('polis_lemonade_17-05-2026.pdf', '/polis.pdf', 1, supplier='lemonade', purpose='polis'),
            _row('factuur_infomedics_17-05-2026.pdf', '/infomedics.pdf', 2, supplier='infomedics', purpose='factuur'),
            _row('factuur_onbekend_17-05-2026.pdf', '/unknown.pdf', 3, supplier='onbekend', purpose='factuur'),
        ]

        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link', return_value='https://example.com/document') as temporary_link,
            patch('bewaarhet.search_reply.send_html') as send_html,
        ):
            send_search_results('user@example.com', 'polis lemonade')

        temporary_link.assert_called_once_with('/polis.pdf')
        html = send_html.call_args.args[2]
        self.assertEqual(html.count('Download document'), 1)
        self.assertIn('polis_lemonade_17-05-2026.pdf', html)
        self.assertNotIn('factuur_infomedics_17-05-2026.pdf', html)
        self.assertNotIn('factuur_onbekend_17-05-2026.pdf', html)

    def test_password_note_is_returned_for_natural_search_request(self) -> None:
        rows = [
            _row(
                'notitie_wachtwoord_aaa_17-05-2026.pdf',
                '/notities/notitie_wachtwoord_aaa_17-05-2026.pdf',
                1,
                purpose='notitie',
                category='notities',
                ocr_text='Wachtwoord: AAEUUUE',
            ),
            _row(
                'factuur_kpn_17-05-2026.pdf',
                '/facturen/factuur_kpn_17-05-2026.pdf',
                2,
                supplier='kpn',
                purpose='factuur',
                category='facturen',
                ocr_text='Factuur KPN. Wachtwoord vergeten? Klik hier.',
            ),
        ]

        output = StringIO()
        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link', return_value='https://example.com/note') as temporary_link,
            patch('bewaarhet.search_reply.send_html') as send_html,
            redirect_stdout(output),
        ):
            send_search_results('user@example.com', 'Ik zoek mijn wachtwoord')

        temporary_link.assert_called_once_with('/notities/notitie_wachtwoord_aaa_17-05-2026.pdf')
        html = send_html.call_args.args[2]
        self.assertIn('notitie_wachtwoord_aaa_17-05-2026.pdf', html)
        self.assertNotIn('factuur_kpn_17-05-2026.pdf', html)
        self.assertIn('[search-debug] sender email: user@example.com', output.getvalue())
        self.assertIn('[search-debug] safe_customer_folder: user_at_example.com', output.getvalue())
        self.assertIn('[search-debug] cleaned query: wachtwoord password login', output.getvalue())
        self.assertIn('[search-debug] candidate records loaded from SQLite: 2', output.getvalue())
        self.assertIn('[search-debug] filename: notitie_wachtwoord_aaa_17-05-2026.pdf', output.getvalue())
        self.assertIn('[search-debug] ocr_text contains query? yes', output.getvalue())

    def test_unrelated_invoice_is_not_returned_for_password_query(self) -> None:
        rows = [
            _row(
                'factuur_kpn_17-05-2026.pdf',
                '/facturen/factuur_kpn_17-05-2026.pdf',
                1,
                supplier='kpn',
                purpose='factuur',
                category='facturen',
                ocr_preview='Factuur KPN. Wachtwoord vergeten? Klik hier.',
                ocr_text='Factuur KPN. Wachtwoord vergeten? Klik hier.',
            ),
        ]

        output = StringIO()
        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link') as temporary_link,
            patch('bewaarhet.search_reply.send_html') as send_html,
            redirect_stdout(output),
        ):
            send_search_results('user@example.com', 'wachtwoord')

        temporary_link.assert_not_called()
        self.assertEqual(send_html.call_args.args[1], 'Geen passend document gevonden')
        self.assertIn('[search-debug] reason rejected: score', output.getvalue())

    def test_real_debug_case_overig_password_text_is_returned(self) -> None:
        rows = [
            _row(
                'overig_youandigoods_17-05-2026.pdf',
                '/overig/overig_youandigoods_17-05-2026.pdf',
                1,
                purpose='',
                category='overig',
                ocr_preview='Wachtwoord AAA: AAEUUUE',
                ocr_text='Wachtwoord AAA: AAEUUUE',
            ),
        ]

        with (
            patch('bewaarhet.search_reply.search_documents', return_value=rows),
            patch('bewaarhet.search_reply.temporary_link', return_value='https://example.com/document') as temporary_link,
            patch('bewaarhet.search_reply.send_html') as send_html,
        ):
            send_search_results('user@example.com', 'zoek wachtwoord')

        temporary_link.assert_called_once_with('/overig/overig_youandigoods_17-05-2026.pdf')
        self.assertEqual(send_html.call_args.args[1], 'Document(en) gevonden')
        self.assertIn('overig_youandigoods_17-05-2026.pdf', send_html.call_args.args[2])


if __name__ == '__main__':
    unittest.main()
