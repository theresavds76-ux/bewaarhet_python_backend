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


def extract_labeled_value(ocr_text: str, labels: list[str], stop_labels: list[str] | None = None) -> str:
    """Extract a value from OCR text after an exact label, inline or on the next line."""
    if not ocr_text:
        return ''

    normalized = (
        ocr_text
        .replace('\r\n', '\n')
        .replace('\r', '\n')
        .replace('\u00a0', ' ')
        .replace('：', ':')
    )
    lines = [re.sub(r'\s+', ' ', line).strip() for line in normalized.split('\n')]
    all_labels = sorted(set(labels + (stop_labels or [])), key=len, reverse=True)
    label_pattern = '|'.join(re.escape(label) for label in all_labels)

    inline_text = re.sub(r'\s+', ' ', normalized).strip()
    wanted_labels = sorted(labels, key=len, reverse=True)
    for label in wanted_labels:
        other_labels = [item for item in all_labels if item.lower() != label.lower()]
        stop_pattern = '|'.join(re.escape(item) for item in other_labels)
        stop_lookup = rf'\s+\b(?:{stop_pattern})\s*[:\-]' if stop_pattern else r'$'
        match = re.search(
            rf'(?i)\b{re.escape(label)}\s*[:\-]\s*(.+?)(?={stop_lookup}|\s*$)',
            inline_text,
        )
        if match:
            value = match.group(1).strip()
            if value:
                return value

    def split_label(line: str) -> tuple[str, str] | None:
        match = re.match(rf'(?i)^({label_pattern})\s*(?:[:\-]\s*)?(.*)$', line)
        if not match:
            return None
        value = (match.group(2) or '').strip()
        if value and any(re.fullmatch(rf'(?i){re.escape(label)}\s*[:\-]?', value) for label in all_labels):
            value = ''
        return match.group(1).lower(), value

    def clean_labeled_value(value: str) -> str:
        return re.sub(r'^\s*[:\-]\s*', '', value or '').strip()

    wanted = {label.lower() for label in labels}
    for index, line in enumerate(lines):
        if not line:
            continue
        parsed = split_label(line)
        if not parsed or parsed[0] not in wanted:
            continue
        if parsed[1]:
            return clean_labeled_value(parsed[1])

        for next_line in lines[index + 1:index + 3]:
            if not next_line:
                continue
            if split_label(next_line):
                break
            value = clean_labeled_value(next_line)
            if value:
                return value
    return ''


def is_generic_supplier_word(value: str | None) -> bool:
    """Check if a word is too generic to be a meaningful supplier."""
    if not value:
        return True
    generic_words = {
        'docs', 'document', 'documenten', 'bijlage', 'bestand', 'attachment',
        'factuur', 'invoice', 'bon', 'receipt', 'scan', 'foto', 'pagina', 'page',
        'bericht', 'e-mail', 'email', 'berichten', 'img', 'image', 'huur', 'huurnota', 'nota',
        'wonen',
        'woningbouw', 'woningcorporatie', 'verhuurder', 'kapsalon', 'salon',
        'garage', 'autobedrijf', 'autoservice', 'energie', 'verzekering',
        'verzekeraar', 'abonnement', 'betaling', 'betaalinformatie',
        'betalingsherinnering', 'certificaat', 'certificate', 'spa'
    }
    return value in generic_words


def has_meaningful_supplier_part(value: str | None) -> bool:
    if not value:
        return False
    return any(part and not is_generic_supplier_word(part) for part in value.split('_'))


def is_randomish_filename_stem(value: str | None) -> bool:
    """Detect camera/random/hash-like filenames that should not become suppliers."""
    if not value:
        return True
    stem = clean_filename(Path(value).stem)
    if not stem:
        return True
    if re.fullmatch(r'img_\d{3,}|dsc_\d{3,}|image_\d{3,}|photo_\d{3,}', stem):
        return True
    if re.fullmatch(r'[0-9a-f]{8,}(-[0-9a-f]{4,})*', stem):
        return True
    if re.fullmatch(r'[a-z0-9]{12,}', stem) and re.search(r'\d', stem):
        return True
    return False


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
    if 'belasting dienst' in header:
        return 'belastingdienst'

    if 'dienst toeslagen' in header:
        return 'dienst_toeslagen'

    # Known supplier keywords. These are checked before generic header extraction
    # so real brands win over descriptive OCR lines.
    supplier_keywords = {
        'belastingdienst': ['belastingdienst'],
        'dienst_toeslagen': ['dienst toeslagen'],
        'greenchoice': ['greenchoice'],
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
        'dhl': ['dhl'],
        'dpd': ['dpd'],
    }

    # Helper to check whole-word matches (for bank names especially)
    def has_whole_word_match(text: str, word: str) -> bool:
        """Check if word appears as whole word in text."""
        pattern = r'\b' + re.escape(word) + r'\b'
        return bool(re.search(pattern, text))

    def detect_named_supplier_from_header(text: str) -> str:
        """Extract likely organization names from the OCR/mail header."""
        blocked_line_phrases = {
            'services rendered',
            'rendered at',
            'invoice details',
            'factuurgegevens',
            'omschrijving',
            'behandeling',
            'betaling',
            'payment',
            'amount',
            'bedrag',
        }
        generic_line_words = {
            'huurnota', 'huur', 'nota', 'factuur', 'invoice', 'document',
            'pagina', 'page', 'datum', 'factuurdatum', 'factuurnummer',
            'onderwerp', 'uw', 'verzoek', 'betalingsregeling', 'betaling',
            'betalingstermijn', 'termijnen', 'bedrag', 'maand', 'overzicht',
            'beschikking', 'aanslag', 'klantnummer', 'relatienummer',
            'debiteur', 'crediteur', 'adres', 'postcode', 'telefoon',
            'services', 'rendered', 'behandeling', 'dienst', 'omschrijving',
            'details', 'amount', 'payment', 'description',
        }
        organization_markers = {
            'wonen', 'energie', 'energy', 'kapsalon', 'salon', 'garage',
            'autobedrijf', 'autoservice', 'autogarage', 'tandarts',
            'praktijk', 'apotheek', 'zorggroep', 'zorg', 'verzekering',
            'verzekeringen', 'verzekeraar', 'telecom', 'installatie',
            'installateur', 'bouw', 'onderhoud', 'diensten', 'service',
            'services', 'groep', 'stichting', 'vereniging', 'dienst',
            'toeslagen', 'bv', 'nv', 'vof',
        }
        raw_lines = (text or '').splitlines()[:12]
        candidate_lines: list[str] = []
        for index, raw_line in enumerate(raw_lines):
            candidate_lines.append(raw_line)
            if index + 1 < len(raw_lines):
                next_line = raw_lines[index + 1].strip()
                if next_line and len(next_line.split()) <= 3:
                    candidate_lines.append(f'{raw_line} {next_line}')

        for raw_line in candidate_lines:
            raw = raw_line.lower()
            if any(phrase in raw for phrase in blocked_line_phrases):
                continue
            if re.search(r'\d{2}[-/]\d{2}[-/]\d{4}|\d{4}[-/]\d{2}[-/]\d{2}', raw_line):
                continue
            cleaned = clean_filename(raw_line)
            if not cleaned:
                continue
            words = [
                word for word in cleaned.split('_')
                if word and word not in generic_line_words and not is_month_name(word)
            ]
            if len(words) > 4:
                continue
            if not any(word in organization_markers for word in words):
                continue
            if not any(not is_generic_supplier_word(word) for word in words):
                continue
            return '_'.join(words)
        return ''

    def clean_organization_candidate(value: str) -> str:
        cleaned = clean_filename(value)
        legal_suffixes = {'bv', 'b.v.', 'nv', 'n.v.', 'ltd', 'limited', 'co', 'company', 'inc'}
        descriptor_words = {'technology', 'technologies'}
        location_prefixes = {'dongguan', 'shenzhen', 'guangzhou', 'ningbo', 'yiwu'}
        words = []
        for word in cleaned.split('_'):
            word = word.strip('.-')
            if (
                not word
                or word in legal_suffixes
                or word in descriptor_words
                or is_generic_supplier_word(word)
                or is_month_name(word)
            ):
                continue
            words.append(word)
        if len(words) > 1 and words[0] in location_prefixes:
            words = words[1:]
        if not words:
            return ''
        return '_'.join(words[:3])

    def detect_labeled_supplier(text: str) -> str:
        candidate = extract_labeled_value(
            text or '',
            ['manufacturer', 'fabrikant', 'supplier', 'leverancier', 'issued by', 'producent'],
            [
                'product name', 'product', 'main model', 'model', 'model no', 'model number',
                'trade mark', 'trademark', 'brand', 'series', 'applicant', 'certificate no',
                'report no', 'standard',
            ],
        )
        candidate = clean_organization_candidate(candidate)
        if candidate and has_meaningful_supplier_part(candidate):
            return candidate
        return ''

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
                continue
            # don't accept generic words
            if is_generic_supplier_word(kw):
                continue
            return name

    labeled_supplier = detect_labeled_supplier(ocr_text or '')
    if labeled_supplier:
        return labeled_supplier

    named_supplier = detect_named_supplier_from_header(header)
    if named_supplier:
        return named_supplier

    # Fallback: search subject and original filename (less weight)
    tail = (subject or '') + '\n' + (original_filename or '')
    tail = tail.lower()
    named_supplier = detect_named_supplier_from_header(tail)
    if named_supplier:
        return named_supplier

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
    if original_filename and not is_randomish_filename_stem(original_filename):
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


def detect_invoice_customer(ocr_text: str) -> str:
    """Return a clearly marked invoice customer, only when it looks business-like."""
    for pattern in [
        r'(?im)^\s*(klant|customer|debiteur|bill to|invoice to)\s*[:\-]\s*(.+)$',
        r'(?im)^\s*(klant|customer|debiteur|bill to|invoice to)\s+(?!nummer\b|number\b|id\b)(.+)$',
        r'(?im)^\s*(klant|customer|debiteur|bill to|invoice to)\s*$\s*^(.+)$',
        r'(?im)^\s*(klantgegevens|customer details)\s*[:\-]?\s*$\s*^(.+)$',
    ]:
        match = re.search(pattern, ocr_text or '')
        if not match:
            continue
        candidate = match.group(match.lastindex or 2).strip()
        cleaned = clean_filename(candidate)
        words = [w for w in cleaned.split('_') if w and not is_generic_supplier_word(w) and not is_month_name(w)]
        while words and words[-1] in {'spa', 'salon', 'kapsalon'}:
            words.pop()
        if not words or len(words) > 4:
            continue
        joined = '_'.join(words)
        raw_words = re.findall(r'[A-Za-z0-9&.-]+', candidate)
        is_upper_acronym = len(raw_words) == 1 and raw_words[0].isupper() and 2 <= len(raw_words[0]) <= 8
        has_business_marker = any(word in {'bv', 'b.v.', 'nv', 'vof', 'stichting', 'vereniging', 'groep'} for word in words)
        has_all_caps_token = any(token.isupper() and 2 <= len(token) <= 8 for token in raw_words)
        has_business_name_signal = '&' in candidate or any(word.lower() in {'nails', 'spa', 'salon', 'kapsalon', 'studio', 'garage', 'wonen'} for word in raw_words)
        if is_upper_acronym or has_business_marker or has_all_caps_token or has_business_name_signal:
            return joined
    return ''


def is_own_outgoing_invoice(ocr_text: str, supplier: str) -> bool:
    """Detect MVP own sales invoices where customer name should lead filename."""
    text = f'{supplier}\n{ocr_text}'.lower()
    text = re.sub(r'[_\-.]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    own_signals = [
        'you and i',
        'youandi',
        'goods service',
        'goods & service',
        'you and i goods',
        'youandi goods service',
    ]
    return any(signal in text for signal in own_signals)


def detect_certificate_filename_parts(ocr_text: str) -> list[str]:
    """Extract manufacturer/model/product parts for compliance certificates."""
    text = ocr_text or ''
    stop_labels = [
        'manufacturer', 'fabrikant', 'supplier', 'leverancier', 'issued by', 'producent',
        'product name', 'product', 'artikel', 'main model', 'model', 'model no',
        'model number', 'type', 'trade mark', 'trademark', 'brand', 'merk',
        'series', 'applicant', 'certificate no', 'report no', 'standard',
        'declaration of conformity',
    ]

    maker = extract_labeled_value(text, ['manufacturer', 'fabrikant'], stop_labels)
    product = extract_labeled_value(text, ['product name', 'product', 'artikel'], stop_labels)
    model = extract_labeled_value(text, ['main model', 'model no', 'model number', 'model', 'type'], stop_labels)

    maker_clean = clean_filename(maker)
    location_prefixes = {'dongguan', 'shenzhen', 'guangzhou', 'ningbo', 'yiwu'}
    maker_words = [
        word.strip('.-') for word in maker_clean.split('_')
        if word.strip('.-') and word.strip('.-') not in {'technology', 'technologies', 'co', 'ltd', 'limited', 'company', 'inc', 'bv', 'nv'}
    ]
    if len(maker_words) > 1 and maker_words[0] in location_prefixes:
        maker_words = maker_words[1:]
    maker_part = '_'.join(maker_words[:2])

    model_part = clean_filename(model).split('_')[0] if model else ''

    product_clean = clean_filename(product)
    product_words = [word for word in product_clean.split('_') if word and word not in {'product', 'device'}]
    product_part = ''.join(product_words[:2]) if product_words[:2] == ['smart', 'lock'] else '_'.join(product_words[:2])

    return [part for part in [maker_part, model_part, product_part] if part]


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

    tax_purposes = {
        'betalingsherinnering',
        'betaalinformatie',
        'betalingsregeling',
        'belastingaanslag',
        'aangifte',
    }
    if supplier in {'belastingdienst', 'dienst_toeslagen'} and purpose in tax_purposes:
        document_type = 'belasting'

    semantic_document_types = {
        'verzendlabel': 'verzendlabel',
        'coc': 'coc',
        'ce_certificaat': 'ce_certificaat',
        'certificaat': 'certificaat',
        'compliance_certificaat': 'compliance_certificaat',
        'offerte': 'offerte',
        'polis': 'polis',
        'aankoopbewijs': 'aankoopbewijs',
        'garantiebewijs': 'garantiebewijs',
    }
    if purpose in semantic_document_types:
        document_type = semantic_document_types[purpose]

    # Supplier provided explicitly (from detect_supplier)
    # Normalize and validate supplier
    if not supplier or is_generic_supplier_word(supplier) or not has_meaningful_supplier_part(supplier):
        supplier = 'onbekend'
    
    # Transform: 'huur' -> 'woningbouw' since huur is a purpose, not a supplier
    # But keep woningbouw as-is
    if supplier == 'huur':
        supplier = 'woningbouw'
    
    # Filter out month names from supplier (they may have leaked in from detect_supplier)
    if supplier and supplier != 'onbekend':
        supplier_parts = supplier.split('_')
        if len(supplier_parts) > 1:
            filtered_parts = [p for p in supplier_parts if p and not is_month_name(p)]
        else:
            filtered_parts = [p for p in supplier_parts if p and not is_month_name(p) and not is_generic_supplier_word(p)]
        if filtered_parts:
            supplier = '_'.join(filtered_parts)
        else:
            supplier = 'onbekend'

    customer = detect_invoice_customer(ocr_text)
    if category == 'facturen' and customer and is_own_outgoing_invoice(ocr_text, supplier):
        supplier = customer

    if category == 'overig' and not purpose and supplier == 'onbekend' and is_randomish_filename_stem(original_filename):
        supplier = clean_filename(Path(original_filename).stem) or supplier

    # Format date for filename as DD-MM-YYYY
    try:
        y, m, d = document_date.split('-')
        display_date = f'{d}-{m}-{y}'
    except Exception:
        display_date = document_date

    if purpose == 'coc':
        certificate_parts = detect_certificate_filename_parts(ocr_text)
        parts = [document_type] + (certificate_parts or [supplier])
        parts.append(display_date)
        filename = '_'.join(parts) + extension
        return clean_filename(filename), document_date

    parts = [document_type, supplier]
    # Avoid adding duplicate purpose when it matches the document type or is generic
    # Also skip if purpose is huur and supplier is woningbouw (redundant)
    generic_purpose = {'document', 'bestand', 'bijlage', 'docs', 'factuur'}
    skip_purpose = purpose == document_type or purpose in generic_purpose or (supplier == 'woningbouw' and purpose == 'huur')
    if purpose and not skip_purpose:
        parts.append(purpose)
    parts.append(display_date)

    filename = '_'.join(parts) + extension

    return clean_filename(filename), document_date


def detect_purpose(ocr_text: str, subject: str) -> str:
    """Detect short purpose tags like 'betalingsregeling', 'aanmaning', 'herinnering', 'aangifte', 'huur', 'factuur', 'bon'.
    
    Rules:
    - betalingsregeling: explicit payment plan mentions, before dunning signals
    - specific purposes like huur/energie/verzekering/abonnement before aanmaning
    - aanmaning: only explicit strong collection/dunning notices
    - factuur: invoices (but lower priority than specific purposes)
    - bon: receipts
    """
    text = f"{subject}\n{ocr_text}".lower()

    payment_plan_terms = [
        'betalingsregeling',
        'betaalregeling',
        'verzoek om een betalingsregeling',
        'verzoek om betalingsregeling',
        'bedrag per maand',
        'in termijnen',
        'termijnen',
    ]
    extreme_collection_terms = [
        'sommatie',
        'ingebrekestelling',
        'deurwaarder',
        'incassokosten',
        'overgedragen aan incasso',
        'laatste aanmaning',
    ]

    if any(term in text for term in payment_plan_terms):
        if any(term in text for term in extreme_collection_terms):
            return 'aanmaning'
        return 'betalingsregeling'

    if 'aangifte' in text or 'belastingaangifte' in text:
        return 'aangifte'

    if 'betalingsherinnering' in text:
        return 'betalingsherinnering'
    if 'betaalinformatie' in text or ('belastingdienst' in text and any(k in text for k in ['rekeningnummer', 'iban', 'termijn', 'betalen', 'betalingskenmerk'])):
        return 'betaalinformatie'

    if any(k in text for k in ['offerte', 'quotation', 'quote number', 'offertenummer']):
        return 'offerte'

    if any(k in text for k in ['verzendlabel', 'pakketlabel', 'brievenbuspakje', 'track & trace', 'track trace']):
        return 'verzendlabel'

    if 'certificate of compliance' in text:
        return 'coc'
    if any(k in text for k in ['declaration of conformity', 'product certificate']):
        return 'compliance_certificaat'
    if any(k in text for k in ['ce certificaat', 'ce certificate', 'certificaat ce']):
        return 'ce_certificaat'
    if 'certificaat' in text or 'certificate' in text:
        return 'certificaat'
    
    # Specific domain/purpose signals come before dunning-like wording.
    if 'huurnota' in text or ('huur' in text and 'nota' in text):
        return 'huur'
    if any(k in text for k in ['huurachterstand', 'huurbetaling', 'huurbetalingsregeling', 'huurincasso']):
        return 'huur'
    if any(k in text for k in ['energienota', 'energiecontract', 'jaarafrekening energie', 'termijnbedrag energie']):
        return 'energie'
    if any(k in text for k in ['polisblad', 'verzekeringspolis', 'polisnummer']):
        return 'polis'
    if any(k in text for k in ['verzekeringspremie', 'premie verzekering']):
        return 'verzekering'
    if any(k in text for k in ['abonnement', 'maandabonnement', 'lidmaatschap']):
        return 'abonnement'
    if any(k in text for k in ['aankoopbewijs', 'proof of purchase', 'purchase receipt']):
        return 'aankoopbewijs'
    if any(k in text for k in ['garantiebewijs', 'warranty certificate', 'garantiecertificaat']):
        return 'garantiebewijs'

    strong_aanmaning_terms = [
        'aanmaning',
        'laatste herinnering',
        'ingebrekestelling',
        'betalingsachterstand',
        'achterstallig',
        'achterstallige',
        'sommatie',
        'incassokosten',
        'deurwaarder',
    ]

    if 'incasso' in text and 'automatische incasso' not in text:
        return 'aanmaning'

    if any(term in text for term in strong_aanmaning_terms):
        return 'aanmaning'
    
    if 'herinnering' in text:
        return 'herinnering'
    
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

    if supplier in {'belastingdienst', 'dienst_toeslagen'}:
        if any(has_phrase(full_text, phrase) for phrase in (
            'betaalinformatie',
            'betalingsherinnering',
            'betalingsregeling',
            'belastingaanslag',
            'betalingskenmerk',
            'te betalen',
        )):
            return 'belasting'

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
            'voorlopige aanslag', 'belastingteruggave', 'dienst toeslagen',
            'toeslagen',
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
