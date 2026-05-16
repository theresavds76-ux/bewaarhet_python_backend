from __future__ import annotations

import re
from html import escape
from pathlib import Path


def safe_customer_folder(email_address: str) -> str:
    return email_address.strip().lower().replace('@', '_at_').replace('+', '_plus_')


def file_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def is_probable_search_email(subject: str, body: str, has_attachments: bool) -> bool:
    if has_attachments:
        return False
    text = f'{subject}\n{body}'.strip().lower()
    search_words = ('zoek', 'vind', 'stuur', 'document', 'bon', 'factuur', 'contract', 'belasting', 'aangifte')
    return any(word in text for word in search_words)


def extract_search_text(subject: str, body: str) -> str:
    text = f'{subject}\n{body}'
    text = re.sub(r'(?i)^(re:|fw:|fwd:)\s*', '', text.strip())
    text = re.sub(r'(?i)\b(zoek|vind|stuur|graag|document|documenten|mijn|de|het|een|naar|voor)\b', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:200]


def html_escape(text: str) -> str:
    return escape(text or '', quote=True)

def clean_filename(text: str) -> str:
    text = text.lower()

    replacements = {
        ' ': '_',
        '/': '-',
        '\\': '-',
        ':': '-',
        ';': '',
        ',': '',
        '__': '_',
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    allowed = 'abcdefghijklmnopqrstuvwxyz0123456789_-.' 
    text = ''.join(c for c in text if c in allowed)

    while '__' in text:
        text = text.replace('__', '_')

    return text.strip('_')


def is_generic_supplier_word(value: str | None) -> bool:
    """Check if a word is too generic to be a meaningful supplier."""
    if not value:
        return True
    generic_words = {
        'docs', 'document', 'documenten', 'bijlage', 'bestand', 'attachment',
        'factuur', 'invoice', 'bon', 'receipt', 'scan', 'foto', 'pagina', 'page',
        'bericht', 'e-mail', 'email', 'berichten'
    }
    return value in generic_words


def is_month_name(value: str | None) -> bool:
    """Check if a word is a month name."""
    if not value:
        return False
    months = {
        'januari', 'februari', 'maart', 'april', 'mei', 'juni',
        'juli', 'augustus', 'september', 'oktober', 'november', 'december',
        'jan', 'feb', 'mrt', 'apr', 'mei', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec',
        'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'
    }
    return value.lower() in months


def is_payment_context_bank(text: str, bank_kw: str) -> bool:
    """Check if a bank keyword appears only in payment/IBAN context, not as issuer.
    Returns True if bank keyword is ONLY in payment context (should skip it as supplier).
    Returns False if bank keyword appears in bank product context (can be supplier).
    """
    if bank_kw not in text.lower():
        return False
    t = text.lower()
    
    # If this is a true bank document (about actual bank products/services), NOT payment context
    true_bank_doc_types = [
        'bankafschrift', 'rekeningafschrift', 'betaalrekening', 'creditcardafschrift',
        'hypotheek', 'spaarrekening', 'lening', 'geldlening', 'krediet', 'insurance',
        'premie', 'polis', 'verzekering', 'belegging'
    ]
    if any(dtype in t for dtype in true_bank_doc_types):
        return False  # This is a bank document, not just payment context
    
    # If it's only mentioned in payment context, skip it as supplier
    payment_clues = ['iban', 'rekening', 'rekeningnummer', 'betaal', 'overboeking', 'betalingskenmerk', 'machtiging', 'incasso']
    return any(clue in t for clue in payment_clues)


def detect_supplier(ocr_text: str, subject: str, original_filename: str, sender_email: str) -> str:
    """Deterministically detect supplier/issuer using strong evidence.

    Priority: sender_email -> OCR top/header -> subject -> original filename
    Returns a cleaned supplier token or 'onbekend'.
    """
    import re
    
    top = (subject or '') + '\n' + (original_filename or '') + '\n' + (ocr_text or '')
    top = top.lower()

    # Strong evidence from sender email
    if sender_email:
        se = sender_email.lower()
        if 'belastingdienst' in se or se.endswith('@belastingdienst.nl'):
            return 'belastingdienst'

    # Strong evidence from OCR header/top
    header = (ocr_text or '')[:500].lower()
    if 'belastingdienst' in header:
        # require explicit mention of Belastingdienst (not just 'btw')
        return 'belastingdienst'

    # Known supplier keywords (checked in header first). Banks handled carefully.
    supplier_keywords = {
        'belastingdienst': ['belastingdienst'],
        'kpn': ['kpn'],
        'ziggo': ['ziggo'],
        'odido': ['odido'],
        'ikea': ['ikea'],
        'kruidvat': ['kruidvat'],
        'jumbo': ['jumbo'],
        'albert_heijn': ['albert heijn', ' ah '],
        'hema': ['hema'],
        'woningbouw': ['woningbouw', 'woningcorporatie', 'verhuurder'],
        'postnl': ['postnl'],
        'bol': ['bol.com'],
        'rabobank': ['rabobank'],
        'ing': ['ing'],
        'abn': ['abn amro', 'abn'],
        'bunq': ['bunq'],
        'paypal': ['paypal'],
    }

    # Helper to check whole-word matches (for bank names especially)
    def has_whole_word_match(text: str, word: str) -> bool:
        """Check if word appears as whole word in text."""
        pattern = r'\b' + re.escape(word) + r'\b'
        return bool(re.search(pattern, text))

    # Check header first for strong matches
    for name, keywords in supplier_keywords.items():
        for kw in keywords:
            # For bank names, require whole-word match to avoid 'ing' in 'Invoice'
            if name in {'ing', 'rabobank', 'abn', 'bunq'}:
                if not has_whole_word_match(header, kw):
                    continue
            elif kw not in header:
                continue
            
            # Special rules
            if name in {'ing', 'rabobank', 'abn', 'bunq'}:
                # don't treat bank as supplier if only mentioned in payment/IBAN context
                if is_payment_context_bank(ocr_text, kw):
                    continue
            if name == 'bol':
                # require stronger bol.com context
                if 'bol.com' in header or 'bestelnummer' in header or 'order' in header or 'klantnummer' in header or 'marketplace' in header:
                    return name
                continue
            if name == 'woningbouw':
                # accept woningbouw if housing-related terms present
                if any(x in header for x in ('huur', 'huurnota', 'woningbouw', 'woningcorporatie')):
                    return name
                continue
            # don't accept generic words
            if is_generic_supplier_word(kw):
                continue
            return name

    # Fallback: search subject and original filename (less weight)
    tail = (subject or '') + '\n' + (original_filename or '')
    tail = tail.lower()
    for name, keywords in supplier_keywords.items():
        for kw in keywords:
            # For bank names, require whole-word match
            if name in {'ing', 'rabobank', 'abn', 'bunq'}:
                if not has_whole_word_match(tail, kw):
                    continue
            elif kw not in tail:
                continue
            
            # ignore generic subjects
            if is_generic_supplier_word(kw):
                continue
            if name in {'ing', 'rabobank', 'abn', 'bunq'} and is_payment_context_bank(tail, kw):
                continue
            if name == 'bol':
                if 'bol.com' in tail or 'bestelnummer' in tail or 'order' in tail or 'klantnummer' in tail:
                    return name
                continue
            return name

    # Subject or filename hint - extract supplier from filename if not generic
    # First try: clean filename (remove generic words, month names)
    if original_filename:
        filename_stem = Path(original_filename).stem
        # Clean: remove generic file-related words
        cleaned = clean_filename(filename_stem)
        # Split by underscore/space and filter: remove generics and month names, but keep single-letter abbreviations
        words = [w for w in cleaned.replace('.', '').split('_') if w and not is_generic_supplier_word(w) and not is_month_name(w)]
        if words:
            filename_hint = '_'.join(words[:3])  # take first 3 meaningful words
            if filename_hint:
                return filename_hint
    
    # Fallback: subject hint (less reliable)
    subject_hint = '_'.join([w for w in clean_filename(subject).replace('.', '').split('_') if len(w) > 2 and not is_month_name(w)][:3])
    if subject_hint and not is_generic_supplier_word(subject_hint):
        return subject_hint
    
    return 'onbekend'

def generate_filename(
    category: str,
    original_filename: str,
    ocr_text: str,
    date_received: str,
    subject: str = '',
    supplier: str = '',
    purpose: str = '',
) -> tuple[str, str]:

    extension = file_extension(original_filename)

    text = f'{subject}\n{ocr_text}'.lower()
    document_date = extract_document_date(text, date_received)

    document_types = {
        'facturen': 'factuur',
        'bonnen': 'bon',
        'contracten': 'contract',
        'belasting': 'belasting',
        'overig': 'overig',
    }

    document_type = document_types.get(category, 'document')

    # Supplier provided explicitly (from detect_supplier)
    # Normalize and validate supplier
    if not supplier or is_generic_supplier_word(supplier):
        supplier = 'onbekend'
    
    # Transform: 'huur' -> 'woningbouw' since huur is a purpose, not a supplier
    # But keep woningbouw as-is
    if supplier == 'huur':
        supplier = 'woningbouw'
    
    # Filter out month names from supplier (they may have leaked in from detect_supplier)
    if supplier and supplier != 'onbekend':
        supplier_parts = supplier.split('_')
        filtered_parts = [p for p in supplier_parts if p and not is_month_name(p) and not is_generic_supplier_word(p)]
        if filtered_parts:
            supplier = '_'.join(filtered_parts)
        else:
            supplier = 'onbekend'

    # Format date for filename as DD-MM-YYYY
    try:
        y, m, d = document_date.split('-')
        display_date = f'{d}-{m}-{y}'
    except Exception:
        display_date = document_date

    parts = [document_type, supplier]
    # Avoid adding duplicate purpose when it matches the document type or is generic
    # Also skip if purpose is huur and supplier is woningbouw (redundant)
    generic_purpose = {'document', 'bestand', 'bijlage', 'docs', 'factuur', 'huur'}
    skip_purpose = purpose == document_type or purpose in generic_purpose or (supplier == 'woningbouw' and purpose == 'huur')
    if purpose and not skip_purpose:
        parts.append(purpose)
    parts.append(display_date)

    filename = '_'.join(parts) + extension

    return clean_filename(filename), document_date


def detect_purpose(ocr_text: str, subject: str) -> str:
    """Detect short purpose tags like 'betalingsregeling', 'aanmaning', 'herinnering', 'aangifte', 'huur', 'factuur', 'bon'.
    
    Rules:
    - betalingsregeling: explicit payment plan mentions
    - aanmaning: dunning/collection notices (priority over other tags)
    - herinnering: reminder notices
    - aangifte: tax filing documents
    - huur: housing/rent-related (huurnota or huur+nota, but NOT when month name only)
    - factuur: invoices (but lower priority than specific purposes)
    - bon: receipts
    """
    text = f"{subject}\n{ocr_text}".lower()

    # Highest priority: collection/dunning notices
    if 'aanmaning' in text or 'incasso' in text:
        return 'aanmaning'
    
    if 'betalingsregeling' in text or 'betaalregeling' in text or 'verzoek om betalingsregeling' in text:
        return 'betalingsregeling'
    if 'herinnering' in text:
        return 'herinnering'
    if 'aangifte' in text or 'belastingaangifte' in text:
        return 'aangifte'
    
    # Huur/housing: huurnota OR (huur + nota), but only if not just a month name
    if 'huurnota' in text or ('huur' in text and 'nota' in text):
        return 'huur'
    # Also accept huur+ huurachterstand, huurbetalng, etc. if more specific context
    if any(k in text for k in ['huurachterstand', 'huurbetaling', 'huurbetalingsregeling', 'huurincasso']):
        return 'huur'
    
    if 'factuur' in text or 'factuurnummer' in text or 'betalingstermijn' in text:
        return 'factuur'
    if any(k in text for k in ('kassabon', 'pinbon', 'bonnetje', 'receipt')):
        return 'bon'
    return ''


def detect_domain(
    ocr_text: str,
    subject: str,
    original_filename: str,
    supplier: str,
    purpose: str,
) -> str:
    """Deterministically detect the life/business domain for a document.

    Returns one of:
    wonen, zorg, verzekeringen, auto, kinderen, werk, belasting, garantie,
    abonnementen, financien, overig.
    """

    def normalize(value: str | None) -> str:
        value = (value or '').lower()
        value = re.sub(r'[_/\\.\-]+', ' ', value)
        value = re.sub(r'\s+', ' ', value).strip()
        return f' {value} ' if value else ' '

    def has_phrase(text: str, phrase: str) -> bool:
        phrase = normalize(phrase).strip()
        if not phrase:
            return False
        pattern = r'(?<![a-z0-9])' + re.escape(phrase).replace(r'\ ', r'\s+') + r'(?![a-z0-9])'
        return bool(re.search(pattern, text))

    filename_stem = Path(original_filename).stem if original_filename else ''
    primary_text = normalize(f'{subject} {filename_stem} {supplier} {purpose}')
    full_text = normalize(f'{subject} {filename_stem} {supplier} {purpose} {ocr_text}')

    domains = [
        'wonen',
        'zorg',
        'verzekeringen',
        'auto',
        'kinderen',
        'werk',
        'belasting',
        'garantie',
        'abonnementen',
        'financien',
    ]
    scores = {domain: 0 for domain in domains}
    matched: dict[str, set[str]] = {domain: set() for domain in domains}

    strong_rules = {
        'wonen': [
            'huurnota', 'huurcontract', 'huurbetaling', 'huurachterstand',
            'woningbouw', 'woningcorporatie', 'verhuurder', 'energienota',
            'jaarafrekening energie', 'waternota', 'tuinman', 'woningonderhoud',
            'beveiligingscentrale', 'alarminstallatie',
        ],
        'zorg': [
            'tandarts', 'huisarts', 'apotheek', 'zorgverzekering', 'ziekenhuis',
            'fysiotherapeut', 'orthodontist', 'ggz', 'eigen risico',
            'patient', 'patientnummer',
        ],
        'verzekeringen': [
            'verzekering', 'verzekeraar', 'polis', 'polisblad', 'schadeclaim',
            'schadeformulier', 'aansprakelijkheidsverzekering',
            'inboedelverzekering', 'reisverzekering', 'levensverzekering',
        ],
        'auto': [
            'auto', 'garage', 'apk', 'kenteken', 'wegenbelasting',
            'motorrijtuigenbelasting', 'autoverzekering', 'leaseauto',
            'onderhoudsbeurt', 'voertuig',
        ],
        'kinderen': [
            'school', 'kinderopvang', 'kinderdagverblijf', 'basisschool',
            'middelbare school', 'bso', 'ouderbijdrage', 'lesgeld',
            'sportclub kind',
        ],
        'werk': [
            'loonstrook', 'salarisstrook', 'werkgever', 'arbeidsovereenkomst',
            'jaaropgave', 'uwv', 'vakantiegeld', 'arbeidscontract',
        ],
        'belasting': [
            'belastingdienst', 'aangifte', 'belastingaangifte', 'aanslag',
            'btw aangifte', 'inkomstenbelasting', 'omzetbelasting',
            'voorlopige aanslag', 'belastingteruggave',
        ],
        'garantie': [
            'garantie', 'aankoopbewijs', 'serienummer', 'retour',
            'retourlabel', 'rma', 'reparatieverzoek',
        ],
        'abonnementen': [
            'abonnement', 'telecom', 'streaming', 'software subscription',
            'subscription', 'lidmaatschap', 'maandabonnement',
        ],
        'financien': [
            'bankafschrift', 'rekeningafschrift', 'betaalrekening',
            'spaarrekening', 'lening', 'hypotheek', 'krediet',
            'creditcard', 'creditcardafschrift', 'betaalverzoek',
        ],
    }

    weak_rules = {
        'wonen': ['huur', 'woning', 'huis', 'energie', 'water', 'onderhoud', 'internet thuis'],
        'zorg': ['medisch', 'zorg', 'behandeling', 'consult'],
        'verzekeringen': ['premie', 'schade'],
        'auto': ['brandstof', 'banden', 'parkeerkosten'],
        'kinderen': ['opvang', 'kind', 'kinderen', 'sportclub'],
        'werk': ['salaris', 'dienstverband', 'arbeid'],
        'belasting': ['btw', 'toeslag', 'beschikking'],
        'garantie': ['bon', 'kassabon', 'reparatie'],
        'abonnementen': ['maandbedrag', 'termijnbedrag', 'software', 'streamingdienst'],
        'financien': ['bank', 'betaling', 'incasso', 'machtiging', 'iban', 'rekening'],
    }

    def add_match(domain: str, phrase: str, points: int) -> None:
        if phrase in matched[domain]:
            return
        matched[domain].add(phrase)
        scores[domain] += points

    for domain, phrases in strong_rules.items():
        for phrase in phrases:
            if has_phrase(primary_text, phrase):
                add_match(domain, phrase, 4)
            elif has_phrase(full_text, phrase):
                add_match(domain, phrase, 3)

    for domain, phrases in weak_rules.items():
        for phrase in phrases:
            if has_phrase(primary_text, phrase):
                add_match(domain, phrase, 2)
            elif has_phrase(full_text, phrase):
                add_match(domain, phrase, 1)

    contextual_rules = [
        ('wonen', 3, ['huur', 'nota']),
        ('wonen', 3, ['huur', 'woning']),
        ('wonen', 3, ['energie', 'jaarafrekening']),
        ('wonen', 3, ['water', 'nota']),
        ('wonen', 3, ['internet', 'thuis']),
        ('wonen', 3, ['tuinman', 'onderhoud']),
        ('wonen', 3, ['beveiliging', 'woning']),
        ('wonen', 3, ['alarm', 'huis']),
        ('zorg', 3, ['zorg', 'factuur']),
        ('zorg', 3, ['medisch', 'declaratie']),
        ('verzekeringen', 3, ['premie', 'polis']),
        ('verzekeringen', 3, ['schade', 'verzekering']),
        ('verzekeringen', 3, ['verzekeraar', 'premie']),
        ('auto', 3, ['auto', 'verzekering']),
        ('auto', 3, ['auto', 'schade']),
        ('auto', 3, ['garage', 'factuur']),
        ('kinderen', 3, ['school', 'kind']),
        ('kinderen', 3, ['sportclub', 'kind']),
        ('werk', 3, ['werkgever', 'contract']),
        ('werk', 3, ['salaris', 'strook']),
        ('belasting', 3, ['btw', 'aangifte']),
        ('belasting', 3, ['belasting', 'aanslag']),
        ('garantie', 3, ['aankoop', 'garantie']),
        ('garantie', 3, ['serienummer', 'garantie']),
        ('garantie', 3, ['retour', 'aankoop']),
        ('abonnementen', 3, ['maandbedrag', 'abonnement']),
        ('abonnementen', 3, ['telecom', 'factuur']),
        ('abonnementen', 3, ['software', 'subscription']),
        ('financien', 3, ['betaling', 'bank']),
        ('financien', 3, ['incasso', 'machtiging']),
        ('financien', 3, ['iban', 'betaling']),
    ]

    for domain, points, phrases in contextual_rules:
        if all(has_phrase(full_text, phrase) for phrase in phrases):
            add_match(domain, ' + '.join(phrases), points)

    if has_phrase(full_text, 'zorgverzekering'):
        scores['verzekeringen'] = max(0, scores['verzekeringen'] - 3)
    if has_phrase(full_text, 'autoverzekering') or has_phrase(full_text, 'wegenbelasting'):
        scores['belasting'] = max(0, scores['belasting'] - 3)
        scores['verzekeringen'] = max(0, scores['verzekeringen'] - 2)

    priority = [
        'auto',
        'zorg',
        'belasting',
        'kinderen',
        'werk',
        'garantie',
        'financien',
        'wonen',
        'verzekeringen',
        'abonnementen',
    ]
    best_domain = max(priority, key=lambda domain: (scores[domain], -priority.index(domain)))
    if scores[best_domain] < 3:
        return 'overig'
    return best_domain


def extract_document_date(text: str, fallback_date: str) -> str:
    import re

    patterns = [
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{2}-\d{2}-\d{4})',
        r'(\d{2}/\d{2}/\d{4})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            date = match.group(1)

            if '/' in date:
                day, month, year = date.split('/')
                return f'{year}-{month}-{day}'

            if len(date.split('-')[0]) == 2:
                day, month, year = date.split('-')
                return f'{year}-{month}-{day}'

            return date

    return fallback_date
