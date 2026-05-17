from __future__ import annotations

import unittest

from bewaarhet.search_reply import _score


def _row(
    filename: str,
    *,
    supplier: str = '',
    purpose: str = '',
    category: str = 'overig',
    domain: str = 'overig',
    ocr_preview: str = '',
    ocr_text: str = '',
    dropbox_path: str = '',
) -> dict[str, str]:
    return {
        'filename': filename,
        'supplier': supplier,
        'purpose': purpose,
        'title': '',
        'original_filename': '',
        'category': category,
        'domain': domain,
        'ocr_preview': ocr_preview,
        'ocr_text': ocr_text,
        'dropbox_path': dropbox_path,
        'year': '2026',
        'month': '05',
    }


class SearchRelevanceTests(unittest.TestCase):
    def test_rekening_vitens_ranks_highest_with_high_score(self) -> None:
        vitens = _row(
            'rekening_vitens_17-05-2026.pdf',
            supplier='vitens',
            purpose='rekening',
            category='facturen',
            domain='wonen',
        )
        unrelated_rekening = _row(
            'rekening_odido_17-05-2026.pdf',
            supplier='odido',
            purpose='rekening',
            category='facturen',
        )
        unrelated_vitens = _row('waternota_vitens_17-05-2026.pdf', supplier='vitens')

        ranked = sorted(
            [unrelated_rekening, vitens, unrelated_vitens],
            key=lambda row: _score(row, 'rekening vitens'),
            reverse=True,
        )

        self.assertEqual(ranked[0]['filename'], 'rekening_vitens_17-05-2026.pdf')
        self.assertGreaterEqual(_score(vitens, 'rekening vitens'), 85)
        self.assertGreater(_score(vitens, 'rekening vitens'), _score(unrelated_rekening, 'rekening vitens'))

    def test_polis_lemonade_ranks_highest_with_high_score(self) -> None:
        lemonade = _row(
            'polis_lemonade_17-05-2026.pdf',
            supplier='lemonade',
            purpose='polis',
            category='verzekeringen',
            domain='verzekeringen',
        )
        unrelated_polis = _row(
            'polis_anwb_17-05-2026.pdf',
            supplier='anwb',
            purpose='polis',
            category='verzekeringen',
        )
        unrelated_lemonade = _row('factuur_lemonade_17-05-2026.pdf', supplier='lemonade')

        ranked = sorted(
            [unrelated_polis, unrelated_lemonade, lemonade],
            key=lambda row: _score(row, 'polis lemonade'),
            reverse=True,
        )

        self.assertEqual(ranked[0]['filename'], 'polis_lemonade_17-05-2026.pdf')
        self.assertGreaterEqual(_score(lemonade, 'polis lemonade'), 85)
        self.assertGreater(_score(lemonade, 'polis lemonade'), _score(unrelated_polis, 'polis lemonade'))

    def test_belastingformulier_matches_belasting_kwijtschelding_strongly(self) -> None:
        tax_form = _row(
            'belasting_gemeentebelastingen_kwijtscheldingsformulier_17-05-2026.pdf',
            supplier='gemeentebelastingen_amstelland',
            purpose='kwijtscheldingsformulier',
            category='belasting',
            domain='belasting',
        )
        unrelated_tax = _row(
            'belasting_belastingdienst_betaalinformatie_17-05-2026.pdf',
            supplier='belastingdienst',
            purpose='betaalinformatie',
            category='belasting',
            domain='belasting',
        )

        self.assertGreaterEqual(_score(tax_form, 'belastingformulier'), 75)
        self.assertGreater(_score(tax_form, 'belastingformulier'), _score(unrelated_tax, 'belastingformulier'))

    def test_unrelated_single_word_matches_stay_lower_than_exact_multi_word_matches(self) -> None:
        exact = _row('rekening_vitens_17-05-2026.pdf', supplier='vitens', purpose='rekening')
        single_match = _row('rekening_onbekend_17-05-2026.pdf', purpose='rekening')
        unrelated = _row('polis_lemonade_17-05-2026.pdf', supplier='lemonade', purpose='polis')

        self.assertLess(_score(single_match, 'rekening vitens'), _score(exact, 'rekening vitens'))
        self.assertLess(_score(unrelated, 'rekening vitens'), _score(exact, 'rekening vitens'))

    def test_long_mixed_query_still_scores_exact_document_pairs_highly(self) -> None:
        query = 'belastingformulier Rekening Vitens Polis Lemonade Huurcontract'
        vitens = _row('rekening_vitens_17-05-2026.pdf', supplier='vitens', purpose='rekening')
        lemonade = _row('polis_lemonade_17-05-2026.pdf', supplier='lemonade', purpose='polis')
        tax_form = _row(
            'belasting_gemeentebelastingen_kwijtscheldingsformulier_17-05-2026.pdf',
            supplier='gemeentebelastingen_amstelland',
            purpose='kwijtscheldingsformulier',
            category='belasting',
            domain='belasting',
        )
        unrelated = _row('factuur_onbekend_17-05-2026.pdf', purpose='factuur')

        self.assertGreaterEqual(_score(vitens, query), 85)
        self.assertGreaterEqual(_score(lemonade, query), 85)
        self.assertGreaterEqual(_score(tax_form, query), 75)
        self.assertLess(_score(unrelated, query), _score(vitens, query))

    def test_stored_note_with_password_label_scores_above_threshold(self) -> None:
        note = _row(
            'notitie_wachtwoord_aaa_17-05-2026.pdf',
            category='notities',
            purpose='notitie',
            ocr_text='Wachtwoord: AAEUUUE',
        )

        self.assertGreaterEqual(_score(note, 'Ik zoek mijn wachtwoord'), 30)

    def test_ww_alias_finds_wachtwoord_note_context(self) -> None:
        note = _row(
            'notitie_wachtwoord_aaa_17-05-2026.pdf',
            category='notities',
            purpose='notitie',
            ocr_text='Wachtwoord voor AAA is AAEUUUE',
        )

        self.assertGreaterEqual(_score(note, 'ww AAA'), 30)

    def test_unrelated_invoice_stays_below_threshold_for_password_query(self) -> None:
        invoice = _row(
            'factuur_kpn_17-05-2026.pdf',
            supplier='kpn',
            purpose='factuur',
            category='facturen',
            ocr_preview='Factuur KPN. Wachtwoord vergeten? Klik hier.',
            ocr_text='Factuur KPN. Wachtwoord vergeten? Klik hier om uw account te herstellen.',
        )

        self.assertLess(_score(invoice, 'wachtwoord'), 30)

    def test_notes_category_gets_credential_relevance_boost(self) -> None:
        note = _row(
            'notitie_17-05-2026.pdf',
            category='notities',
            purpose='notitie',
            ocr_text='wachtwoord: AAEUUUE',
        )
        non_note = _row(
            'document_17-05-2026.pdf',
            category='overig',
            ocr_text='wachtwoord: AAEUUUE',
        )

        self.assertGreater(_score(note, 'wachtwoord'), _score(non_note, 'wachtwoord'))
        self.assertGreaterEqual(_score(note, 'wachtwoord'), 30)

    def test_real_debug_case_overig_password_text_scores_above_threshold(self) -> None:
        candidate = _row(
            'overig_youandigoods_17-05-2026.pdf',
            category='overig',
            purpose='',
            ocr_preview='Wachtwoord AAA: AAEUUUE',
            ocr_text='Wachtwoord AAA: AAEUUUE',
        )

        self.assertGreaterEqual(_score(candidate, 'zoek wachtwoord'), 30)


if __name__ == '__main__':
    unittest.main()
