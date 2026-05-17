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


if __name__ == '__main__':
    unittest.main()
