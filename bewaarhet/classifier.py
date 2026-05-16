from __future__ import annotations

from .config import settings

CATEGORIES = {'facturen', 'bonnen', 'contracten', 'belasting', 'overig'}

KEYWORDS = {
    'facturen': [
        'factuur', 'invoice', 'factuurnummer', 'invoice number', 'betalingstermijn',
        'vervaldatum', 'factuurdatum', 'debiteur', 'crediteur', 'leverancier',
        'klantnummer', 'iban', 'btw-id', 'kvk', 'offerte'
    ],
    'contracten': [
        'contract', 'overeenkomst', 'algemene voorwaarden', 'voorwaarden', 'looptijd',
        'ondertekening', 'handtekening', 'partijen', 'opdrachtgever', 'opdrachtnemer',
        'ingangsdatum', 'beëindiging', 'beeindiging', 'agreement', 'terms', 'policy',
        'clausule', 'huur', 'huurovereenkomst', 'abonnement'
    ],
    'belasting': [
        'belastingdienst', 'belastingbrief', 'inkomstenbelasting', 'inkomsten belasting',
        'omzetbelasting', 'btw-aangifte', 'aanslag', 'voorlopige aanslag', 'toeslagen',
        'loonheffing'
    ],
    'bonnen': [
        'kassabon', 'pinbon', 'bonnetje', 'betaling met pas', 'contactloos',
        'transactie', 'receipt', 'betaalautomaat', 'bedankt voor uw bezoek', 'hema',
        'action', 'jumbo', 'albert heijn', ' ah ', 'kruidvat', 'blokker', 'ikea',
        'lidl', 'aldi', 'plus', 'hoogvliet', 'etos', 'gamma', 'praxis', 'mediamarkt'
    ],
}


def classify_rules(text: str, filename: str = '', subject: str = '', snippet: str = '') -> str:
    haystack = f' {text} {filename} {subject} {snippet} '.lower()
    for category in ('belasting', 'contracten', 'bonnen', 'facturen'):
        if any(keyword in haystack for keyword in KEYWORDS[category]):
            return category
    return 'twijfel'


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
