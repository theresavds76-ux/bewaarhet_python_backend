from __future__ import annotations

from typing import Dict, List
import re

from .config import settings

CATEGORIES = {'facturen', 'bonnen', 'contracten', 'belasting', 'overig'}


# Weighted keyword lists. Strong > medium > weak.
WEIGHTS = {
    'facturen': {
        'strong': [
            'factuur', 'invoice', 'factuurnummer', 'invoice number', 'factuurnummer',
            'betalingstermijn', 'vervaldatum', 'factuurdatum'
        ],
        'medium': ['nota', 'huurnota', 'betaling', 'betaald', 'totaal', 'bedrag'],
        'weak': ['btw', 'iban', 'kvk', 'klantnummer']
    },
    'bonnen': {
        'strong': ['kassabon', 'pinbon', 'bonnetje', 'receipt', 'transactie'],
        'medium': ['betaalautomaat', 'bedankt voor uw bezoek', 'contactloos'],
        'weak': []
    },
    'contracten': {
        'strong': ['contract', 'overeenkomst', 'algemene voorwaarden', 'voorwaarden', 'looptijd', 'handtekening', 'ondertekening', 'partijen', 'ingangsdatum', 'beëindiging', 'clausule', 'huurovereenkomst'],
        'medium': ['opzeg', 'opzegging', 'abonnement'],
        'weak': ['huur']
    },
    'belasting': {
        'strong': [
            'belastingdienst', 'dienst toeslagen', 'aanslag', 'voorlopige aanslag',
            'aanslagnummer', 'belastingaangifte', 'aangifteformulier',
            'inkomstenbelasting', 'loonheffing', 'betalingsregeling',
            'betalingsherinnering', 'betaalinformatie', 'belastingaanslag'
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


def classify_rules(text: str, filename: str = '', subject: str = '', snippet: str = '') -> str:
    haystack = f'{subject}\n{filename}\n{snippet}\n{text}'.lower()

    label_signals = ['verzendlabel', 'pakketlabel', 'brievenbuspakje', 'track trace', 'track & trace', 'barcode']
    carrier_signals = ['postnl', 'dhl', 'dpd']
    invoice_signals = ['factuurnummer', 'invoice number', 'factuurdatum', 'btw-bedrag', 'subtotal', 'subtotaal']
    if any(carrier in haystack for carrier in carrier_signals) and any(signal in haystack for signal in label_signals):
        if not any(signal in haystack for signal in invoice_signals):
            return 'overig'
    if 'betaalopdracht' in haystack and not any(signal in haystack for signal in invoice_signals):
        return 'overig'

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

    # Avoid single weak matches dominating: require a minimal score
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_cat, top_score = sorted_scores[0]
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0

    # If no evidence, return 'twijfel' to trigger fallback
    if top_score == 0:
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
                        'Classificeer een Nederlands document in exact één lowercase woord uit: '
                        'facturen, bonnen, contracten, belasting, overig. '
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
