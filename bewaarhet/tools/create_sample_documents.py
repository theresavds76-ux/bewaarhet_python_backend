from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[2]
TESTDATA = ROOT / 'testdata' / 'documents'


SAMPLES = [
    {
        'id': 'invoice_kpn',
        'folder': 'invoices',
        'filename': 'kpn_factuur_juni_2026.txt',
        'subject': 'Factuur KPN juni 2026',
        'text': '''
            KPN B.V.
            Factuur
            Factuurnummer: KPN-2026-0601
            Factuurdatum: 01-06-2026
            Klantnummer: 123456
            Internet en mobiel abonnement
            Subtotaal: 24,79
            BTW-bedrag: 5,21
            Totaalbedrag: EUR 30,00
            Te betalen voor 15-06-2026
        ''',
        'expected': {'category': 'facturen', 'supplier': 'kpn', 'filename_contains': ['factuur', 'kpn', '2026'], 'search_queries': ['zoek mijn KPN factuur', 'factuur internet'], 'min_ocr_chars': 80},
    },
    {
        'id': 'receipt_bol',
        'folder': 'receipts',
        'filename': 'bol_aankoopbewijs_2026.txt',
        'subject': 'Aankoopbewijs bol.com',
        'text': '''
            bol.com
            Aankoopbewijs
            Besteldatum: 03-06-2026
            Ordernummer: 4012345678
            Artikel: USB-C kabel
            Betaald met iDEAL
            Totaal: EUR 12,99
            Bedankt voor je aankoop.
        ''',
        'expected': {'category': 'bonnen', 'supplier': 'bol', 'filename_contains': ['aankoopbewijs', 'bol', '2026'], 'search_queries': ['zoek bon van bol', 'zoek aankoopbewijs kabel'], 'min_ocr_chars': 60},
    },
    {
        'id': 'policy_lemonade',
        'folder': 'policies',
        'filename': 'lemonade_polisblad_2026.txt',
        'subject': 'Polisblad inboedelverzekering',
        'text': '''
            Lemonade Insurance N.V.
            Polisblad
            Polisnummer: LEM-2026-8842
            Ingangsdatum: 01-06-2026
            Inboedelverzekering
            Verzekerde: Demo Gebruiker
            Premie per maand: EUR 8,50
        ''',
        'expected': {'category': 'overig', 'supplier': 'lemonade', 'filename_contains': ['polis', 'lemonade', '2026'], 'search_queries': ['zoek polis', 'zoek lemonade verzekering'], 'min_ocr_chars': 60},
    },
    {
        'id': 'contract_ziggo',
        'folder': 'contracts',
        'filename': 'ziggo_contract_2026.txt',
        'subject': 'Contract Ziggo internet',
        'text': '''
            Ziggo Services B.V.
            Overeenkomst internet abonnement
            Contractnummer: ZIG-2026-1188
            Ingangsdatum: 10-06-2026
            Looptijd: 12 maanden
            Partijen: Ziggo en Demo Gebruiker
            Ondertekening digitaal bevestigd.
        ''',
        'expected': {'category': 'contracten', 'supplier': 'ziggo', 'filename_contains': ['contract', 'ziggo', '2026'], 'search_queries': ['zoek contract', 'zoek ziggo overeenkomst'], 'min_ocr_chars': 70},
    },
    {
        'id': 'tax_belastingdienst',
        'folder': 'tax',
        'filename': 'belastingdienst_aanslag_2026.txt',
        'subject': 'Voorlopige aanslag inkomstenbelasting',
        'text': '''
            Belastingdienst
            Voorlopige aanslag inkomstenbelasting 2026
            Aanslagnummer: 2026.1234.567
            Dagtekening: 05-06-2026
            Te betalen bedrag: EUR 245,00
            Betalingskenmerk: 123456789
            Rekeningnummer: NL86INGB0002445588
        ''',
        'expected': {'category': 'belasting', 'supplier': 'belastingdienst', 'filename_contains': ['belasting', 'belastingdienst', '2026'], 'search_queries': ['zoek belastingaanslag', 'zoek aanslag inkomstenbelasting'], 'min_ocr_chars': 80},
    },
    {
        'id': 'general_note',
        'folder': 'general',
        'filename': 'notitie_meterstanden_2026.txt',
        'subject': 'Notitie meterstanden',
        'text': '''
            Notitie
            Meterstanden opgenomen op 07-06-2026.
            Elektra hoog: 12345
            Elektra laag: 9876
            Gas: 4567
            Bewaren voor controle jaarafrekening.
        ''',
        'expected': {'category': 'notities', 'supplier': '', 'filename_contains': ['notitie', '2026'], 'search_queries': ['zoek meterstanden', 'zoek jaarafrekening controle'], 'min_ocr_chars': 50},
    },
    {
        'id': 'bad_quality_receipt_jumbo',
        'folder': 'bad_quality',
        'filename': 'jumbo_bon_slechte_scan.png',
        'subject': 'Slechte scan kassabon Jumbo',
        'text': '''
            JUMBO
            Kassabon
            Datum: 08-06-2026
            Brood 2,49
            Melk 1,29
            Contactloos betaald
            Totaal EUR 3,78
            Bedankt voor uw bezoek
        ''',
        'expected': {'category': 'bonnen', 'supplier': 'jumbo', 'filename_contains': ['bon', 'jumbo', '2026'], 'search_queries': ['zoek jumbo bon', 'zoek kassabon melk'], 'min_ocr_chars': 40},
        'image': 'bad',
    },
]


def _write_text_sample(sample: dict, folder: Path) -> Path:
    path = folder / sample['filename']
    text = dedent(sample['text']).strip() + '\n'
    path.write_text(text, encoding='utf-8')
    path.with_suffix(path.suffix + '.ocr.txt').write_text(text, encoding='utf-8')
    return path


def _write_image_sample(sample: dict, folder: Path) -> Path:
    path = folder / sample['filename']
    text = dedent(sample['text']).strip()
    image = Image.new('RGB', (900, 620), color=(238, 238, 226))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    y = 36
    for line in text.splitlines():
        draw.text((42, y), line, fill=(25, 25, 25), font=font)
        y += 34
    image = image.rotate(-4, expand=True, fillcolor=(40, 40, 40)).filter(ImageFilter.GaussianBlur(radius=0.7))
    image.save(path)
    path.with_suffix(path.suffix + '.ocr.txt').write_text(text + '\n', encoding='utf-8')
    return path


def main() -> None:
    for folder in ['invoices', 'receipts', 'policies', 'contracts', 'tax', 'general', 'bad_quality']:
        (TESTDATA / folder).mkdir(parents=True, exist_ok=True)

    expected_entries = []
    for sample in SAMPLES:
        folder = TESTDATA / sample['folder']
        path = _write_image_sample(sample, folder) if sample.get('image') else _write_text_sample(sample, folder)
        expected_entries.append({
            'id': sample['id'],
            'path': str(path.relative_to(TESTDATA)).replace('\\', '/'),
            'subject': sample['subject'],
            'date_received': '2026-06-09',
            'expected': sample['expected'],
        })

    (TESTDATA / 'expected.json').write_text(json.dumps({'documents': expected_entries}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Created {len(expected_entries)} sample documents in {TESTDATA}')


if __name__ == '__main__':
    main()
