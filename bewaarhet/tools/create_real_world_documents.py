from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance


ROOT = Path(__file__).resolve().parents[2]
TESTDATA = ROOT / 'testdata' / 'real_world_documents'


SAMPLES = [
    {
        'id': 'shadow_tax_assessment',
        'folder': 'tax',
        'filename': 'schaduw_belastingaanslag.png',
        'subject': 'Foto belastingaanslag met schaduw',
        'variant': 'shadow',
        'text': '''
            Belastingdienst
            Voorlopige aanslag inkomstenbelasting 2026
            Aanslagnummer: 2026.555.123
            Dagtekening: 04-06-2026
            Te betalen bedrag EUR 118,00
            Betalingskenmerk 555123
        ''',
        'expected': {'category': 'belasting', 'supplier': 'belastingdienst', 'filename_contains': ['belasting', 'belastingdienst', '2026'], 'search_queries': ['belastingaanslag', 'belastingdienst aanslag'], 'ocr_terms': ['belastingdienst', 'aanslag', 'inkomstenbelasting'], 'min_ocr_chars': 60, 'min_ocr_score': 0.67},
    },
    {
        'id': 'lowres_health_policy',
        'folder': 'policies',
        'filename': 'lage_resolutie_zorgverzekering.png',
        'subject': 'Lage resolutie zorgverzekering polis',
        'variant': 'lowres',
        'text': '''
            ZorgZeker Verzekeringen
            Polisblad zorgverzekering
            Polisnummer ZZ-2026-4411
            Ingangsdatum 01-01-2026
            Eigen risico EUR 385
            Premie per maand EUR 142,50
        ''',
        'expected': {'category': 'overig', 'supplier': '', 'filename_contains': ['polis', '2026'], 'search_queries': ['zorgverzekering', 'zoek polis'], 'ocr_terms': ['polisblad', 'zorgverzekering', 'premie'], 'min_ocr_chars': 55, 'min_ocr_score': 0.67},
    },
    {
        'id': 'cropped_energy_contract',
        'folder': 'contracts',
        'filename': 'afgesneden_energiecontract.png',
        'subject': 'Afgesneden energiecontract',
        'variant': 'cropped',
        'text': '''
            Greenchoice
            Energiecontract
            Contractnummer GC-2026-8821
            Ingangsdatum 15-06-2026
            Looptijd 12 maanden
            Tarief elektriciteit en gas
            Ondertekening digitaal akkoord
        ''',
        'expected': {'category': 'contracten', 'supplier': 'greenchoice', 'filename_contains': ['contract', 'greenchoice', '2026'], 'search_queries': ['contract energie', 'greenchoice contract'], 'ocr_terms': ['energiecontract', 'contractnummer', 'looptijd'], 'min_ocr_chars': 65, 'min_ocr_score': 0.67},
    },
    {
        'id': 'stamped_laptop_invoice',
        'folder': 'invoices',
        'filename': 'gestempelde_laptop_factuur.png',
        'subject': 'Factuur laptop met stempel',
        'variant': 'stamp',
        'text': '''
            TechStore Demo B.V.
            Factuur
            Factuurnummer TS-2026-7788
            Factuurdatum 06-06-2026
            Laptop model X
            Subtotaal EUR 825,62
            BTW-bedrag EUR 173,38
            Totaalbedrag EUR 999,00
            BETAALD
        ''',
        'expected': {'category': 'facturen', 'supplier': 'techstore_demo', 'filename_contains': ['factuur', 'techstore', '2026'], 'search_queries': ['factuur laptop', 'techstore factuur'], 'ocr_terms': ['factuur', 'factuurnummer', 'laptop'], 'min_ocr_chars': 75, 'min_ocr_score': 0.67},
    },
    {
        'id': 'handwritten_praxis_receipt',
        'folder': 'receipts',
        'filename': 'bon_praxis_handgeschreven.png',
        'subject': 'Praxis bon met handgeschreven notitie',
        'variant': 'handwritten',
        'text': '''
            PRAXIS
            Kassabon
            Datum 07-06-2026
            Schroeven 4,99
            Verfroller 6,49
            Contactloos betaald
            Totaal EUR 11,48
            Notitie: badkamer plank
        ''',
        'expected': {'category': 'bonnen', 'supplier': '', 'filename_contains': ['bon', '2026'], 'search_queries': ['bon praxis', 'verfroller bon'], 'ocr_terms': ['praxis', 'kassabon', 'totaal'], 'min_ocr_chars': 55, 'min_ocr_score': 0.67},
    },
    {
        'id': 'multilingual_recipe_note',
        'folder': 'general',
        'filename': 'recept_appeltaart_meertalig.png',
        'subject': 'Recept appeltaart',
        'variant': 'rotated',
        'text': '''
            Notitie recept appeltaart
            Ingredients / Ingredienten
            Appels 1 kilo
            Bloem 300 gram
            Kaneel
            Suiker
            Oven 180 graden
            Bewaren als familierecept.
        ''',
        'expected': {'category': 'notities', 'supplier': '', 'filename_contains': ['notitie', 'recept'], 'search_queries': ['recept appeltaart', 'familierecept'], 'ocr_terms': ['appeltaart', 'bloem', 'kaneel'], 'min_ocr_chars': 50, 'min_ocr_score': 0.67},
    },
    {
        'id': 'multipage_telecom_invoice',
        'folder': 'invoices',
        'filename': 'telecom_factuur_meerdere_paginas.txt',
        'subject': 'Meerdere pagina telecom factuur',
        'variant': 'text',
        'text': '''
            Pagina 1 van 2
            Odido
            Factuur
            Factuurnummer OD-2026-9001
            Factuurdatum 02-06-2026
            Mobiel abonnement

            Pagina 2 van 2
            Specificatie verbruik
            Totaalbedrag EUR 26,50
            BTW EUR 4,60
            Te betalen voor 16-06-2026
        ''',
        'expected': {'category': 'facturen', 'supplier': 'odido', 'filename_contains': ['factuur', 'odido', '2026'], 'search_queries': ['telecom factuur', 'odido rekening'], 'ocr_terms': ['factuur', 'factuurnummer', 'totaalbedrag'], 'min_ocr_chars': 80, 'min_ocr_score': 0.67},
    },
]


def _font():
    return ImageFont.load_default()


def _base_image(text: str) -> Image.Image:
    image = Image.new('RGB', (950, 720), color=(244, 241, 232))
    draw = ImageDraw.Draw(image)
    y = 34
    for line in dedent(text).strip().splitlines():
        draw.text((45, y), line.strip(), fill=(25, 25, 25), font=_font())
        y += 34
    return image


def _apply_variant(image: Image.Image, variant: str) -> Image.Image:
    if variant == 'shadow':
        overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.polygon([(560, 0), (950, 0), (950, 720), (720, 720)], fill=(0, 0, 0, 80))
        return Image.alpha_composite(image.convert('RGBA'), overlay).convert('RGB').rotate(-3, expand=True, fillcolor=(35, 35, 35))
    if variant == 'lowres':
        small = image.resize((420, 320))
        return small.resize((950, 720)).filter(ImageFilter.GaussianBlur(radius=0.8))
    if variant == 'cropped':
        return image.crop((0, 38, 870, 690)).rotate(2, expand=True, fillcolor=(235, 235, 235))
    if variant == 'stamp':
        draw = ImageDraw.Draw(image)
        draw.rectangle((620, 90, 835, 170), outline=(170, 0, 0), width=5)
        draw.text((660, 118), 'BETAALD', fill=(170, 0, 0), font=_font())
        return image.rotate(-2, expand=True, fillcolor=(40, 40, 40))
    if variant == 'handwritten':
        draw = ImageDraw.Draw(image)
        draw.line((520, 450, 760, 520), fill=(30, 60, 180), width=3)
        draw.text((535, 470), 'klus', fill=(30, 60, 180), font=_font())
        return ImageEnhance.Brightness(image.rotate(4, expand=True, fillcolor=(45, 45, 45))).enhance(0.82)
    if variant == 'rotated':
        return image.rotate(-6, expand=True, fillcolor=(235, 235, 235)).filter(ImageFilter.GaussianBlur(radius=0.35))
    return image


def _write_sample(sample: dict) -> dict:
    folder = TESTDATA / sample['folder']
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / sample['filename']
    text = dedent(sample['text']).strip() + '\n'
    if sample['variant'] == 'text':
        path.write_text(text, encoding='utf-8')
    else:
        image = _apply_variant(_base_image(text), sample['variant'])
        image.save(path)
    path.with_suffix(path.suffix + '.ocr.txt').write_text(text, encoding='utf-8')
    return {
        'id': sample['id'],
        'path': str(path.relative_to(TESTDATA)).replace('\\', '/'),
        'subject': sample['subject'],
        'variant': sample['variant'],
        'date_received': '2026-06-09',
        'expected': sample['expected'],
    }


def main() -> None:
    for folder in ['invoices', 'receipts', 'policies', 'contracts', 'tax', 'general', 'bad_quality']:
        (TESTDATA / folder).mkdir(parents=True, exist_ok=True)
    entries = [_write_sample(sample) for sample in SAMPLES]
    (TESTDATA / 'expected.json').write_text(json.dumps({'documents': entries}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Created {len(entries)} real-world style documents in {TESTDATA}')


if __name__ == '__main__':
    main()
