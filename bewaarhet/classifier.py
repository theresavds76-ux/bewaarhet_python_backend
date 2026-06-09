from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
import re

from .config import settings
from .utils import is_note_like_content

CATEGORIES = {'facturen', 'bonnen', 'contracten', 'belasting', 'notities', 'overig'}


@dataclass(frozen=True)
class ClassificationResult:
    category: str
    confidence: float
    reason: str
    method: str = 'rules'
    rule_confidence: float = 0.0
    fallback_threshold: float = 0.65
    ai_fallback_enabled: bool = False
    ai_fallback_used: bool = False
    ai_fallback_considered: bool = False
    ai_fallback_reason: str = 'not evaluated'
    ocr_sufficient_for_ai: bool = False
    alternative_categories: tuple[str, ...] = ()


# Weighted keyword lists. Strong > medium > weak.
WEIGHTS = {
    'facturen': {
        'strong': [
            'factuur', 'invoice', 'factuurnummer', 'invoice number', 'factuurnummer',
            'invoice#', 'invoice #', 'betalingstermijn', 'vervaldatum', 'factuurdatum',
            'due date', 'annual subscription fee', 'subscription fee', 'vat'
        ],
        'medium': ['nota', 'huurnota', 'betaling', 'betaald', 'totaal', 'bedrag'],
        'weak': ['btw', 'iban', 'kvk', 'klantnummer']
    },
    'bonnen': {
        'strong': ['kassabon', 'pinbon', 'bonnetje', 'receipt', 'transactie', 'aankoopbewijs'],
        'medium': ['betaalautomaat', 'bedankt voor uw bezoek', 'contactloos', 'ordernummer', 'besteldatum'],
        'weak': []
    },
    'contracten': {
        'strong': ['contract', 'overeenkomst', 'algemene voorwaarden', 'voorwaarden', 'looptijd', 'handtekening', 'ondertekening', 'partijen', 'ingangsdatum', 'beÃ«indiging', 'clausule', 'huurovereenkomst'],
        'medium': ['opzeg', 'opzegging', 'abonnement'],
        'weak': ['huur']
    },
    'belasting': {
        'strong': [
            'belastingdienst', 'dienst toeslagen', 'aanslag', 'voorlopige aanslag',
            'aanslagnummer', 'belastingaangifte', 'aangifteformulier',
            'inkomstenbelasting', 'loonheffing', 'betalingsregeling',
            'betalingsherinnering', 'betaalinformatie', 'belastingaanslag',
            'kwijtschelding', 'kwijtscheldingsformulier', 'gemeentebelastingen'
        ],
        'medium': ['aangifte', 'omzetbelasting', 'btw-aangifte', 'belastingbetaling', 'termijn', 'termijnen'],
        'weak': ['btw']
    }
}


def _count_matches(haystack: str, phrase: str) -> int:
    # match whole words/phrases case-insensitive
    try:
        pattern = r"\b" + re.escape(phrase) + r"\b"
        return len(re.findall(pattern, haystack))
    except re.error:
        return 0


def _has_invoice_evidence(haystack: str) -> bool:
    evidence_terms = [
        'factuur',
        'invoice',
        'factuurnummer',
        'invoice number',
        'invoice#',
        'invoice #',
        'factuurdatum',
        'betalingstermijn',
        'vervaldatum',
        'totaalbedrag',
        'btw-bedrag',
        'subtotal',
        'subtotaal',
    ]
    return any(_count_matches(haystack, term) for term in evidence_terms)


def _has_receipt_evidence(haystack: str) -> bool:
    evidence_terms = [
        'kassabon',
        'pinbon',
        'bonnetje',
        'aankoopbewijs',
        'receipt',
        'contactloos betaald',
        'bedankt voor uw bezoek',
    ]
    return any(_count_matches(haystack, term) for term in evidence_terms)


def _has_contract_evidence(haystack: str) -> bool:
    evidence_terms = [
        'contract',
        'overeenkomst',
        'algemene voorwaarden',
        'looptijd',
        'handtekening',
        'ondertekening',
        'clausule',
        'huurovereenkomst',
        'contractnummer',
    ]
    return any(_count_matches(haystack, term) for term in evidence_terms)


def _confidence_from_scores(top_score: int, second_score: int) -> float:
    margin = top_score - second_score
    return round(min(0.98, 0.55 + (top_score * 0.04) + (margin * 0.03)), 2)


def _ocr_sufficient_for_ai(text: str, subject: str = '', filename: str = '', snippet: str = '') -> bool:
    combined = f'{subject}\n{filename}\n{snippet}\n{text}'.strip()
    return len(combined) >= 40


def _result_with_ai_decision(
    category: str,
    confidence: float,
    reason: str,
    *,
    method: str = 'rules',
    allow_ai_fallback: bool,
    ai_fallback_used: bool = False,
    ai_fallback_considered: bool = False,
    ai_fallback_reason: str,
    ocr_sufficient_for_ai: bool,
    alternative_categories: tuple[str, ...] = (),
) -> ClassificationResult:
    return ClassificationResult(
        category,
        confidence,
        reason,
        method,
        rule_confidence=confidence,
        ai_fallback_enabled=bool(allow_ai_fallback and settings.openai_api_key),
        ai_fallback_used=ai_fallback_used,
        ai_fallback_considered=ai_fallback_considered,
        ai_fallback_reason=ai_fallback_reason,
        ocr_sufficient_for_ai=ocr_sufficient_for_ai,
        alternative_categories=alternative_categories,
    )


def _maybe_ai_fallback(
    text: str,
    filename: str,
    subject: str,
    snippet: str,
    *,
    allow_ai_fallback: bool,
    fallback_reason: str,
    fallback_confidence: float,
    alternative_categories: tuple[str, ...],
) -> ClassificationResult:
    ocr_sufficient = _ocr_sufficient_for_ai(text, subject, filename, snippet)
    if not allow_ai_fallback:
        reason = 'AI fallback disabled for this run'
    elif not settings.openai_api_key:
        reason = 'AI fallback unavailable: OPENAI_API_KEY not configured'
    elif not ocr_sufficient:
        reason = 'AI fallback skipped: OCR/context too short'
    else:
        fallback = classify_openai(text, filename, subject, snippet)
        return _result_with_ai_decision(
            fallback,
            0.55 if fallback != 'overig' else fallback_confidence,
            f'{fallback_reason}; AI fallback used',
            method='fallback',
            allow_ai_fallback=allow_ai_fallback,
            ai_fallback_used=True,
            ai_fallback_considered=True,
            ai_fallback_reason='AI fallback called because rule confidence was too low or ambiguous',
            ocr_sufficient_for_ai=ocr_sufficient,
            alternative_categories=alternative_categories,
        )

    return _result_with_ai_decision(
        'overig',
        fallback_confidence,
        f'{fallback_reason}; fallback not called',
        allow_ai_fallback=allow_ai_fallback,
        ai_fallback_considered=True,
        ai_fallback_reason=reason,
        ocr_sufficient_for_ai=ocr_sufficient,
        alternative_categories=alternative_categories,
    )


def classify_rules(text: str, filename: str = '', subject: str = '', snippet: str = '') -> str:
    haystack = f'{subject}\n{filename}\n{snippet}\n{text}'.lower()

    if (
        (is_note_like_content(text, subject, filename) or is_note_like_content(snippet, subject, filename))
        and not _has_receipt_evidence(haystack)
        and not _has_invoice_evidence(haystack)
    ):
        return 'notities'

    if 'recept' in haystack and any(term in haystack for term in ['ingredient', 'ingredienten', 'ingrediÃ«nten', 'bloem', 'kaneel', 'oven']):
        return 'notities'

    advice_signals = [
        'adviesdocument',
        'juridisch advies',
        'ons advies',
        'advies van',
        'advies van het juridisch loket',
    ]
    if any(signal in haystack for signal in advice_signals):
        return 'overig'

    tax_form_signals = ['kwijtschelding', 'kwijtscheldingsformulier']
    if any(signal in haystack for signal in tax_form_signals):
        return 'belasting'

    tax_authority_signals = ['belastingdienst', 'belasting dienst', 'dienst toeslagen']
    tax_payment_signals = [
        'betaalinformatie', 'betalingsherinnering', 'belastingaanslag',
        'betalingskenmerk', 'te betalen', 'rekeningnummer', 'iban',
        'termijn', 'datum waarop betaald moet zijn'
    ]
    if any(signal in haystack for signal in tax_authority_signals) and any(signal in haystack for signal in tax_payment_signals):
        return 'belasting'

    label_signals = ['verzendlabel', 'pakketlabel', 'brievenbuspakje', 'track trace', 'track & trace', 'barcode']
    carrier_signals = ['postnl', 'dhl', 'dpd']
    invoice_signals = ['factuurnummer', 'invoice number', 'factuurdatum', 'btw-bedrag', 'subtotal', 'subtotaal']
    if any(carrier in haystack for carrier in carrier_signals) and any(signal in haystack for signal in label_signals):
        if not any(signal in haystack for signal in invoice_signals):
            return 'overig'
    if 'betaalopdracht' in haystack and not any(signal in haystack for signal in invoice_signals):
        return 'overig'

    invoice_document_signals = [
        'invoice', 'invoice#', 'invoice #', 'invoice number', 'factuur',
        'factuurnummer', 'factuurdatum', 'annual subscription fee',
        'subscription fee', 'due date',
    ]
    receipt_only_signals = ['kassabon', 'pinbon', 'bonnetje', 'betaalautomaat', 'contactloos']

    scores: Dict[str, int] = {c: 0 for c in CATEGORIES}

    # scoring weights
    weight_map = {'strong': 3, 'medium': 2, 'weak': 1}

    for category, groups in WEIGHTS.items():
        for strength, phrases in groups.items():
            w = weight_map.get(strength, 1)
            for phrase in phrases:
                matches = _count_matches(haystack, phrase)
                if matches:
                    scores[category] += matches * w

    # Special handling for 'nota' and 'huurnota' to favor facturen
    # BUT: if belastingdienst context, don't favor facturen
    if (_count_matches(haystack, 'nota') or _count_matches(haystack, 'huurnota')):
        if 'belastingdienst' not in haystack:
            scores['facturen'] += 2
    
    # Strong belasting signals: belastingdienst + betalingsregeling/aanslag/etc.
    if 'belastingdienst' in haystack or 'dienst toeslagen' in haystack:
        if any(sig in haystack for sig in ['betalingsregeling', 'aanslag', 'inkomstenbelasting', 'loonheffing', 'omzetbelasting', 'aangifteformulier', 'betaalinformatie', 'betalingsherinnering', 'belastingaanslag']):
            scores['belasting'] += 5  # strong boost

    if any(_count_matches(haystack, signal) for signal in invoice_document_signals):
        scores['facturen'] += 4
        if not any(signal in haystack for signal in receipt_only_signals):
            scores['bonnen'] = max(0, scores['bonnen'] - 3)

    # Avoid single weak matches dominating: require a minimal score
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_cat, top_score = sorted_scores[0]
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0

    # If no evidence, return 'twijfel' to trigger fallback
    if top_score == 0:
        return 'twijfel'

    if top_cat == 'facturen' and not _has_invoice_evidence(haystack):
        return 'twijfel'
    if top_cat == 'contracten' and not _has_contract_evidence(haystack):
        return 'twijfel'

    # If top is not sufficiently stronger than second, return 'twijfel'
    if top_score - second_score < 2:
        return 'twijfel'

    # Otherwise return the top category (only the allowed set)
    return top_cat


def classify_openai(text: str, filename: str = '', subject: str = '', snippet: str = '') -> str:
    if not settings.openai_api_key:
        return 'overig'
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0,
            max_tokens=3,
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'Classificeer een Nederlands document in exact Ã©Ã©n lowercase woord uit: '
                        'facturen, bonnen, contracten, belasting, notities, overig. '
                        'Gebruik OCR-tekst eerst. Als OCR leeg of slecht is, gebruik bestandsnaam, onderwerp en snippet. '
                        'Het woord btw alleen is niet genoeg voor belasting. Geef alleen het categorie-woord terug.'
                    ),
                },
                {
                    'role': 'user',
                    'content': f'Bestandsnaam: {filename}\nOnderwerp: {subject}\nSnippet: {snippet}\nOCR: {text[:1500]}',
                },
            ],
        )
        answer = (response.choices[0].message.content or '').strip().lower()
        for category in CATEGORIES:
            if category in answer:
                return category
        return 'overig'
    except Exception:
        return 'overig'


def classify_document(text: str, filename: str = '', subject: str = '', snippet: str = '') -> str:
    category = classify_rules(text, filename, subject, snippet)
    if category != 'twijfel':
        return category
    return classify_openai(text, filename, subject, snippet)


def classify_document_with_reason(
    text: str,
    filename: str = '',
    subject: str = '',
    snippet: str = '',
    *,
    allow_ai_fallback: bool = True,
) -> ClassificationResult:
    haystack = f'{subject}\n{filename}\n{snippet}\n{text}'.lower()
    ocr_sufficient = _ocr_sufficient_for_ai(text, subject, filename, snippet)

    if (
        (is_note_like_content(text, subject, filename) or is_note_like_content(snippet, subject, filename))
        and not _has_receipt_evidence(haystack)
        and not _has_invoice_evidence(haystack)
    ):
        return _result_with_ai_decision(
            'notities',
            0.92,
            'note-like content detected',
            allow_ai_fallback=allow_ai_fallback,
            ai_fallback_reason='AI fallback skipped: high-confidence rule match',
            ocr_sufficient_for_ai=ocr_sufficient,
        )
    if 'recept' in haystack and any(term in haystack for term in ['ingredient', 'ingredienten', 'ingrediënten', 'bloem', 'kaneel', 'oven']):
        return _result_with_ai_decision(
            'notities',
            0.9,
            'recipe/note content detected',
            allow_ai_fallback=allow_ai_fallback,
            ai_fallback_reason='AI fallback skipped: high-confidence rule match',
            ocr_sufficient_for_ai=ocr_sufficient,
        )

    scores: Dict[str, int] = {c: 0 for c in CATEGORIES}
    weight_map = {'strong': 3, 'medium': 2, 'weak': 1}
    matched: dict[str, list[str]] = {category: [] for category in CATEGORIES}

    for category, groups in WEIGHTS.items():
        for strength, phrases in groups.items():
            weight = weight_map.get(strength, 1)
            for phrase in phrases:
                matches = _count_matches(haystack, phrase)
                if matches:
                    scores[category] += matches * weight
                    matched[category].append(f'{strength}:{phrase}')

    if (_count_matches(haystack, 'nota') or _count_matches(haystack, 'huurnota')) and 'belastingdienst' not in haystack:
        scores['facturen'] += 2
        matched['facturen'].append('boost:nota')

    if 'belastingdienst' in haystack or 'dienst toeslagen' in haystack:
        if any(sig in haystack for sig in ['betalingsregeling', 'aanslag', 'inkomstenbelasting', 'loonheffing', 'omzetbelasting', 'aangifteformulier', 'betaalinformatie', 'betalingsherinnering', 'belastingaanslag']):
            scores['belasting'] += 5
            matched['belasting'].append('boost:belastingdienst context')

    invoice_document_signals = [
        'invoice', 'invoice#', 'invoice #', 'invoice number', 'factuur',
        'factuurnummer', 'factuurdatum', 'annual subscription fee',
        'subscription fee', 'due date',
    ]
    receipt_only_signals = ['kassabon', 'pinbon', 'bonnetje', 'betaalautomaat', 'contactloos']
    if any(_count_matches(haystack, signal) for signal in invoice_document_signals):
        scores['facturen'] += 4
        matched['facturen'].append('boost:invoice document signal')
        if not any(signal in haystack for signal in receipt_only_signals):
            scores['bonnen'] = max(0, scores['bonnen'] - 3)

    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_category, top_score = sorted_scores[0]
    second_category, second_score = sorted_scores[1]
    alternative_categories = tuple(f'{category}:{score}' for category, score in sorted_scores[:3])

    if top_score == 0:
        return _maybe_ai_fallback(
            text,
            filename,
            subject,
            snippet,
            allow_ai_fallback=allow_ai_fallback,
            fallback_reason='no strong rule evidence',
            fallback_confidence=0.2,
            alternative_categories=alternative_categories,
        )

    if top_category == 'facturen' and not _has_invoice_evidence(haystack):
        return _maybe_ai_fallback(
            text,
            filename,
            subject,
            snippet,
            allow_ai_fallback=allow_ai_fallback,
            fallback_reason='invoice score lacked invoice evidence',
            fallback_confidence=0.25,
            alternative_categories=alternative_categories,
        )
    if top_category == 'contracten' and not _has_contract_evidence(haystack):
        return _maybe_ai_fallback(
            text,
            filename,
            subject,
            snippet,
            allow_ai_fallback=allow_ai_fallback,
            fallback_reason='contract score lacked contract evidence',
            fallback_confidence=0.25,
            alternative_categories=alternative_categories,
        )

    margin = top_score - second_score
    confidence = _confidence_from_scores(top_score, second_score)
    if margin < 2:
        return _maybe_ai_fallback(
            text,
            filename,
            subject,
            snippet,
            allow_ai_fallback=allow_ai_fallback,
            fallback_reason=f'classification ambiguous: {top_category}={top_score}, {second_category}={second_score}',
            fallback_confidence=0.3,
            alternative_categories=alternative_categories,
        )

    reason_terms = ', '.join(matched[top_category][:5]) or f'score {top_score}'
    return _result_with_ai_decision(
        top_category,
        confidence,
        f'{top_category} won with score {top_score}; evidence: {reason_terms}',
        allow_ai_fallback=allow_ai_fallback,
        ai_fallback_reason='AI fallback skipped: rule confidence above threshold',
        ocr_sufficient_for_ai=ocr_sufficient,
        alternative_categories=alternative_categories,
    )
