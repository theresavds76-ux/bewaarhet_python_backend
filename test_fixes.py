#!/usr/bin/env python3
"""Test script to validate classification and supplier detection fixes."""

from bewaarhet.classifier import classify_document
from bewaarhet.utils import detect_supplier, detect_purpose, detect_domain, generate_filename, is_document_email_without_attachment


class TestMail:
    def __init__(self, subject, body_text, from_email='user@example.com'):
        self.subject = subject
        self.body_text = body_text
        self.from_email = from_email
        self.attachments = []

    @property
    def has_attachments(self):
        return False

def test_case(name, ocr_text, filename, subject, sender_email='test@test.com', date_received='2025-08-13'):
    """Test a single case and print results."""
    print(f"\n{'='*80}")
    print(f"TEST: {name}")
    print(f"{'='*80}")
    print(f"Filename: {filename}")
    print(f"Subject: {subject}")
    print(f"OCR Text (first 300 chars): {ocr_text[:300]}")
    print()
    
    category = classify_document(ocr_text, filename, subject, ocr_text[:200])
    supplier = detect_supplier(ocr_text, subject, filename, sender_email)
    purpose = detect_purpose(ocr_text, subject, filename)
    new_filename, doc_date = generate_filename(
        category, filename, ocr_text, date_received, subject, supplier, purpose
    )
    
    print(f"Category: {category}")
    print(f"Supplier: {supplier}")
    print(f"Purpose: {purpose}")
    print(f"Generated Filename: {new_filename}")
    print(f"Document Date: {doc_date}")
    
    return category, supplier, purpose, new_filename


# Test Case 1: B Nails (should be b_nails, not ing)
print("\n\n" + "█"*80)
print("TEST CASE 1: B Nails Invoice")
print("█"*80)

ocr_1 = """
Invoice Details
Date: 13-08-2025
Amount: €45.00
Services rendered at salon

Thank you for visiting B Nails!
"""

cat1, sup1, pur1, fn1 = test_case(
    "B Nails Invoice",
    ocr_1,
    "factuur B Nails.pdf",
    "Invoice from B Nails",
)

print(f"\nEXPECTED: category=facturen, supplier=b_nails, filename contains b_nails")
print(f"ACTUAL: category={cat1}, supplier={sup1}, filename={fn1}")
assert cat1 == 'facturen', f"Category should be facturen, got {cat1}"
assert 'b_nails' in fn1, f"Filename should contain 'b_nails', got {fn1}"


# Test Case 2: WSD (should be wsd, not ing)
print("\n\n" + "█"*80)
print("TEST CASE 2: WSD Invoice")
print("█"*80)

ocr_2 = """
Invoice
Date: 20-01-2026
Customer: Jane Doe
Services: Cleaning
Total: €150.00

Invoice from WSD Services
"""

cat2, sup2, pur2, fn2 = test_case(
    "WSD Invoice",
    ocr_2,
    "factuur WSD.pdf",
    "Invoice from WSD",
)

print(f"\nEXPECTED: category=facturen, supplier=wsd, purpose=''")
print(f"ACTUAL: category={cat2}, supplier={sup2}, purpose={pur2}")
assert cat2 == 'facturen', f"Category should be facturen, got {cat2}"
assert sup2 == 'wsd', f"Supplier should be wsd, got {sup2}"


# Test Case 3: Belastingdienst Betalingsregeling (should be belasting, not facturen)
print("\n\n" + "█"*80)
print("TEST CASE 3: Belastingdienst Betalingsregeling")
print("█"*80)

ocr_3 = """
BELASTINGDIENST

Betalingsregeling Aanvraag

Geachte heer/mevrouw,

Uw betalingsregeling is goedgekeurd.
Pagina 1 van 2
"""

cat3, sup3, pur3, fn3 = test_case(
    "Belastingdienst Betalingsregeling",
    ocr_3,
    "betalingsregeling belastingdienst pagina 1.jpg",
    "betalingsregeling belastingdienst pagina 1",
    sender_email='test@belastingdienst.nl'
)

print(f"\nEXPECTED: category=belasting, supplier=belastingdienst, purpose=betalingsregeling")
print(f"ACTUAL: category={cat3}, supplier={sup3}, purpose={pur3}")
assert cat3 == 'belasting', f"Category should be belasting, got {cat3}"
assert sup3 == 'belastingdienst', f"Supplier should be belastingdienst, got {sup3}"
assert pur3 == 'betalingsregeling', f"Purpose should be betalingsregeling, got {pur3}"


# Test Case 4: Huur Oktober (should be woningbouw, not huur_oktober)
print("\n\n" + "█"*80)
print("TEST CASE 4: Huur Oktober")
print("█"*80)

ocr_4 = """
Huurnota Oktober 2025

Betaling volgende:
Huurbetaling: €850.00

Betalingsgegevens: IBAN NL91 ABNA 0417 1643 00
BIC: ABNANL2A

Aanmaning voor achterstallige huurbetalingen
"""

cat4, sup4, pur4, fn4 = test_case(
    "Huur Oktober",
    ocr_4,
    "huur oktober.jpg",
    "huur oktober",
)

print(f"\nEXPECTED: category=facturen, generic huur supplier ignored, purpose=huur")
print(f"ACTUAL: category={cat4}, supplier={sup4}, purpose={pur4}, filename={fn4}")
assert sup4 != 'huur', f"Supplier should not be generic huur, got {sup4}"
assert 'woningbouw' not in fn4, f"Filename should not contain generic woningbouw, got {fn4}"
assert 'oktober' not in fn4.lower(), f"Filename should not contain 'oktober', got {fn4}"
assert pur4 == 'huur', f"Purpose should stay huur for huurnota documents, got {pur4}"


# Test Case 4b: Cazas Wonen huurnota with normal payment instruction
print("\n\n" + "â–ˆ"*80)
print("TEST CASE 4b: Cazas Wonen Huurnota")
print("â–ˆ"*80)

ocr_4b = """
Cazas
Wonen
Huurnota

Factuurdatum: 01-11-2025
Huurbetaling november 2025

Wij verzoeken u het bedrag van EUR 850,00 uiterlijk 14-11-2025 te voldoen.
U kunt nu betalen via de betaallink.
"""

cat4b, sup4b, pur4b, fn4b = test_case(
    "Cazas Wonen Huurnota",
    ocr_4b,
    "cazas wonen huurnota.jpg",
    "Cazas Wonen huurnota november",
)
domain4b = detect_domain(ocr_4b, "Cazas Wonen huurnota november", "cazas wonen huurnota.jpg", sup4b, pur4b)

print(f"\nEXPECTED: category=facturen, supplier=cazas_wonen, purpose=huur, domain=wonen")
print(f"ACTUAL: category={cat4b}, supplier={sup4b}, purpose={pur4b}, domain={domain4b}, filename={fn4b}")
assert cat4b == 'facturen', f"Category should be facturen, got {cat4b}"
assert sup4b == 'cazas_wonen', f"Supplier should be cazas_wonen, got {sup4b}"
assert pur4b == 'huur', f"Purpose should be huur for normal huurnota, got {pur4b}"
assert domain4b == 'wonen', f"Domain should be wonen, got {domain4b}"
assert fn4b == 'factuur_cazas_wonen_huur_01-11-2025.jpg', f"Unexpected filename: {fn4b}"


# Test Case 4c: Generic organization-name extraction
print("\n\n" + "â–ˆ"*80)
print("TEST CASE 4c: Generic Supplier Extraction")
print("â–ˆ"*80)

green_supplier = detect_supplier("Greenchoice\nEnergienota\nTermijnbedrag energie", "Greenchoice energienota", "energienota.pdf", "noreply@greenchoice.nl")
salon_supplier = detect_supplier("Kapsalon Bella\nFactuur\nKnippen en stylen", "Factuur kapsalon", "factuur.pdf", "info@kapsalonbella.nl")
garage_supplier = detect_supplier("Garage Jansen\nFactuur APK onderhoud", "Factuur garage", "factuur.pdf", "info@garagejansen.nl")

print(f"Greenchoice supplier: {green_supplier}")
print(f"Salon supplier: {salon_supplier}")
print(f"Garage supplier: {garage_supplier}")
assert green_supplier == 'greenchoice', f"Supplier should be greenchoice, got {green_supplier}"
assert salon_supplier == 'kapsalon_bella', f"Supplier should be kapsalon_bella, got {salon_supplier}"
assert garage_supplier == 'garage_jansen', f"Supplier should be garage_jansen, got {garage_supplier}"


# Test Case 4d: Dienst Toeslagen betalingsregeling should not become aanmaning
print("\n\n" + "â–ˆ"*80)
print("TEST CASE 4d: Dienst Toeslagen Betalingsregeling")
print("â–ˆ"*80)

ocr_4d = """
Dienst Toeslagen

Datum: 16-05-2026
Onderwerp: Uw verzoek om een betalingsregeling

U hebt een betalingsregeling voor de volgende beschikking(en).
De betalingsregeling betaald u in termijnen.
Het bedrag per maand staat in dit overzicht.
Als u niet op tijd betaalt, kunnen wij de regeling stoppen.
"""

cat4d, sup4d, pur4d, fn4d = test_case(
    "Dienst Toeslagen Betalingsregeling",
    ocr_4d,
    "dienst toeslagen betalingsregeling.jpg",
    "Uw verzoek om een betalingsregeling",
)
domain4d = detect_domain(ocr_4d, "Uw verzoek om een betalingsregeling", "dienst toeslagen betalingsregeling.jpg", sup4d, pur4d)

print(f"\nEXPECTED: category=belasting, supplier=dienst_toeslagen, purpose=betalingsregeling, domain=belasting")
print(f"ACTUAL: category={cat4d}, supplier={sup4d}, purpose={pur4d}, domain={domain4d}, filename={fn4d}")
assert cat4d == 'belasting', f"Category should be belasting, got {cat4d}"
assert sup4d in {'belastingdienst', 'dienst_toeslagen'}, f"Supplier should be belastingdienst or dienst_toeslagen, got {sup4d}"
assert pur4d == 'betalingsregeling', f"Purpose should be betalingsregeling, got {pur4d}"
assert domain4d == 'belasting', f"Domain should be belasting, got {domain4d}"
assert fn4d in {
    'belasting_belastingdienst_betalingsregeling_16-05-2026.jpg',
    'belasting_dienst_toeslagen_betalingsregeling_16-05-2026.jpg',
}, f"Unexpected filename: {fn4d}"


# Test Case 4e: Belastingdienst betaalinformatie / betalingsherinnering
print("\n\n" + "â–ˆ"*80)
print("TEST CASE 4e: Belastingdienst Betalingsherinnering")
print("â–ˆ"*80)

ocr_4e = """
Belastingdienst

Betaalinformatie
Betalingsherinnering belastingaanslag
Datum: 16-05-2026
Termijn: 1
Rekeningnummer/IBAN Belastingdienst: NL86INGB0002445588
"""

cat4e, sup4e, pur4e, fn4e = test_case(
    "Belastingdienst Betalingsherinnering",
    ocr_4e,
    "IMG_6661.jpeg",
    "betaalinformatie",
    date_received='2026-05-16',
)
domain4e = detect_domain(ocr_4e, "betaalinformatie", "IMG_6661.jpeg", sup4e, pur4e)

print(f"\nEXPECTED: category=belasting, supplier=belastingdienst, purpose=betalingsherinnering, domain=belasting")
print(f"ACTUAL: category={cat4e}, supplier={sup4e}, purpose={pur4e}, domain={domain4e}, filename={fn4e}")
assert cat4e == 'belasting', f"Category should be belasting, got {cat4e}"
assert sup4e == 'belastingdienst', f"Supplier should be belastingdienst, got {sup4e}"
assert pur4e == 'betalingsherinnering', f"Purpose should be betalingsherinnering, got {pur4e}"
assert domain4e == 'belasting', f"Domain should be belasting, got {domain4e}"
assert fn4e == 'belasting_belastingdienst_betalingsherinnering_16-05-2026.jpeg', f"Unexpected filename: {fn4e}"


# Test Case 4e2: Belastingdienst payment photo with non-semantic original filename
print("\n\n" + "â–ˆ"*80)
print("TEST CASE 4e2: Belastingdienst Testje Filename")
print("â–ˆ"*80)

ocr_4e2 = """
Belastingdienst

Betaalinformatie
Betalingsherinnering
Factuur / betaling
Te betalen: EUR 128,00
Rekeningnummer / IBAN: NL86INGB0002445588
Betalingskenmerk: 1234 5678 9012 3456
Termijn: betaal voor 15-05-2026
"""

cat4e2, sup4e2, pur4e2, fn4e2 = test_case(
    "Belastingdienst Testje Filename",
    ocr_4e2,
    "testje.jpeg",
    "",
    date_received='2026-05-15',
)
domain4e2 = detect_domain(ocr_4e2, "", "testje.jpeg", sup4e2, pur4e2)

print(f"\nEXPECTED: category=belasting, supplier=belastingdienst, purpose=betalingsherinnering, no testje in filename")
print(f"ACTUAL: category={cat4e2}, supplier={sup4e2}, purpose={pur4e2}, domain={domain4e2}, filename={fn4e2}")
assert cat4e2 == 'belasting', f"Category should be belasting, got {cat4e2}"
assert sup4e2 == 'belastingdienst', f"Supplier should be belastingdienst, got {sup4e2}"
assert pur4e2 in {'betalingsherinnering', 'betaalinformatie'}, f"Purpose should be betalingsherinnering or betaalinformatie, got {pur4e2}"
assert domain4e2 == 'belasting', f"Domain should be belasting, got {domain4e2}"
assert fn4e2 in {
    'belasting_belastingdienst_betalingsherinnering_15-05-2026.jpeg',
    'belasting_belastingdienst_betaalinformatie_15-05-2026.jpeg',
}, f"Unexpected filename: {fn4e2}"
assert 'testje' not in fn4e2, f"Filename should not keep non-semantic original stem, got {fn4e2}"
assert not fn4e2.startswith(('factuur_onbekend', 'overig_testje')), f"Tax filename priority failed: {fn4e2}"


# Test Case 4f: Certificate of Compliance with random filename
print("\n\n" + "â–ˆ"*80)
print("TEST CASE 4f: Certificate of Compliance")
print("â–ˆ"*80)

ocr_4f = """
Certificate of Compliance
CE
Manufacturer:
Dongguan Qishengda Technology Co., Ltd
Product Name:
Smart Lock
Main Model:
D2
Declaration of Conformity
"""

cat4f, sup4f, pur4f, fn4f = test_case(
    "Certificate of Compliance",
    ocr_4f,
    "7eeba915-3a9b-4f2c-8d1e-abcdef123456.jpg",
    "",
    date_received='2026-05-16',
)

print(f"\nEXPECTED: category=overig, supplier=qishengda_technology, purpose=coc")
print(f"ACTUAL: category={cat4f}, supplier={sup4f}, purpose={pur4f}, filename={fn4f}")
assert cat4f == 'overig', f"Category should be overig, got {cat4f}"
assert sup4f.startswith('qishengda'), f"Supplier should start with qishengda, got {sup4f}"
assert pur4f == 'coc', f"Purpose should be coc, got {pur4f}"
assert fn4f == 'coc_qishengda_d2_smartlock_16-05-2026.jpg', f"Filename should be semantic COC certificate, got {fn4f}"
assert '7eeba915' not in fn4f, f"Filename should not use random stem, got {fn4f}"


# Test Case 4g: Plain photo without document OCR keeps IMG-style name
print("\n\n" + "â–ˆ"*80)
print("TEST CASE 4g: Plain Photo")
print("â–ˆ"*80)

cat4g, sup4g, pur4g, fn4g = test_case(
    "Plain Photo",
    "",
    "IMG_6652.jpeg",
    "",
    date_received='2026-05-15',
)

print(f"\nEXPECTED: category=overig, filename keeps img_6652")
print(f"ACTUAL: category={cat4g}, supplier={sup4g}, purpose={pur4g}, filename={fn4g}")
assert cat4g == 'overig', f"Category should be overig, got {cat4g}"
assert pur4g == '', f"Purpose should be empty, got {pur4g}"
assert fn4g == 'overig_img_6652_15-05-2026.jpeg', f"Plain photo filename should keep IMG stem, got {fn4g}"


# Test Case 4h: PostNL shipping label is not an invoice
print("\n\n" + "â–ˆ"*80)
print("TEST CASE 4h: PostNL Verzendlabel")
print("â–ˆ"*80)

ocr_4h = """
PostNL
Verzendlabel
Brievenbuspakje
Track & Trace: 3SABCD1234567
Afzender
Ontvanger
"""

cat4h, sup4h, pur4h, fn4h = test_case(
    "PostNL Verzendlabel",
    ocr_4h,
    "IMG_6670.jpeg",
    "",
    date_received='2026-05-15',
)
domain4h = detect_domain(ocr_4h, "", "IMG_6670.jpeg", sup4h, pur4h)

print(f"\nEXPECTED: category=overig, supplier=postnl, purpose=verzendlabel")
print(f"ACTUAL: category={cat4h}, supplier={sup4h}, purpose={pur4h}, domain={domain4h}, filename={fn4h}")
assert cat4h == 'overig', f"Category should be overig, got {cat4h}"
assert sup4h == 'postnl', f"Supplier should be postnl, got {sup4h}"
assert pur4h == 'verzendlabel', f"Purpose should be verzendlabel, got {pur4h}"
assert domain4h == 'overig', f"Domain should be overig, got {domain4h}"
assert fn4h == 'verzendlabel_postnl_15-05-2026.jpeg', f"Unexpected filename: {fn4h}"


# Test Case 4i: Outgoing invoice with clear customer WSD
print("\n\n" + "â–ˆ"*80)
print("TEST CASE 4i: Verkoopfactuur Klant WSD")
print("â–ˆ"*80)

ocr_4i = """
You and I
Goods & Service
Invoice
Invoice Date: 20-01-2026
Klant WSD
Jeroen van Leeuwen
Total: EUR 150.00
"""

cat4i, sup4i, pur4i, fn4i = test_case(
    "Verkoopfactuur Klant WSD",
    ocr_4i,
    "factuur Goods Service.pdf",
    "Invoice from Goods Service",
)

print(f"\nEXPECTED: category=facturen, filename uses customer WSD")
print(f"ACTUAL: category={cat4i}, supplier={sup4i}, purpose={pur4i}, filename={fn4i}")
assert cat4i == 'facturen', f"Category should be facturen, got {cat4i}"
assert fn4i == 'factuur_wsd_20-01-2026.pdf', f"Filename should use WSD customer, got {fn4i}"


# Test Case 4j: Outgoing invoice with clear customer B Nails & Spa
print("\n\n" + "â–ˆ"*80)
print("TEST CASE 4j: Verkoopfactuur Klant B Nails & Spa")
print("â–ˆ"*80)

ocr_4j = """
You and I
Goods & Service
Invoice
Invoice Date: 13-08-2025
Klant B Nails & Spa
Services rendered
Total: EUR 45.00
"""

cat4j, sup4j, pur4j, fn4j = test_case(
    "Verkoopfactuur Klant B Nails & Spa",
    ocr_4j,
    "factuur Goods Service.pdf",
    "Invoice from Goods Service",
)

print(f"\nEXPECTED: category=facturen, filename uses customer B Nails")
print(f"ACTUAL: category={cat4j}, supplier={sup4j}, purpose={pur4j}, filename={fn4j}")
assert cat4j == 'facturen', f"Category should be facturen, got {cat4j}"
assert fn4j == 'factuur_b_nails_13-08-2025.pdf', f"Filename should use B Nails customer, got {fn4j}"


# Test Case 4k: Semantic offerte filename from IMG file
print("\n\n" + "â–ˆ"*80)
print("TEST CASE 4k: Semantic Offerte Filename")
print("â–ˆ"*80)

ocr_4k = """
Garage Jansen
Offerte
Offertenummer: O-2026-014
Datum: 17-05-2026
Onderhoudsbeurt en APK
"""

cat4k, sup4k, pur4k, fn4k = test_case(
    "Semantic Offerte Filename",
    ocr_4k,
    "IMG_7777.jpg",
    "",
    date_received='2026-05-17',
)

print(f"\nEXPECTED: purpose=offerte, filename=offerte_garage_jansen_17-05-2026.jpg")
print(f"ACTUAL: category={cat4k}, supplier={sup4k}, purpose={pur4k}, filename={fn4k}")
assert pur4k == 'offerte', f"Purpose should be offerte, got {pur4k}"
assert fn4k == 'offerte_garage_jansen_17-05-2026.jpg', f"Unexpected filename: {fn4k}"


# Test Case 4l: Semantic polis filename from image file
print("\n\n" + "â–ˆ"*80)
print("TEST CASE 4l: Semantic Polis Filename")
print("â–ˆ"*80)

ocr_4l = """
ANWB Verzekering
Polisblad
Polisnummer: P-123456
Datum: 17-05-2026
Autoverzekering
"""

cat4l, sup4l, pur4l, fn4l = test_case(
    "Semantic Polis Filename",
    ocr_4l,
    "image_8888.jpeg",
    "",
    date_received='2026-05-17',
)

print(f"\nEXPECTED: purpose=polis, filename=polis_anwb_verzekering_17-05-2026.jpeg")
print(f"ACTUAL: category={cat4l}, supplier={sup4l}, purpose={pur4l}, filename={fn4l}")
assert pur4l == 'polis', f"Purpose should be polis, got {pur4l}"
assert fn4l == 'polis_anwb_verzekering_17-05-2026.jpeg', f"Unexpected filename: {fn4l}"


# Test Case 5: ING Bank Statement (should be ing, not payment context)
print("\n\n" + "█"*80)
print("TEST CASE 5: ING Bank Statement")
print("█"*80)

ocr_5 = """
ING Rekeningafschrift
Juni 2025

Rekeningnummer: NL91 INGB 0001 2345 67
Periode: 01-06-2025 tot 30-06-2025

Saldo: €5,234.56
"""

cat5, sup5, pur5, fn5 = test_case(
    "ING Bank Statement",
    ocr_5,
    "bankafschrift juni.pdf",
    "ING rekeningafschrift",
    sender_email='info@ing.nl'
)

print(f"\nEXPECTED: category=overig, supplier=ing (TRUE bank document)")
print(f"ACTUAL: category={cat5}, supplier={sup5}, purpose={pur5}")
assert sup5 == 'ing', f"Supplier should be ing for true bank document, got {sup5}"


# Test Case 6: Payment instruction with ING (should skip ING as supplier)
print("\n\n" + "█"*80)
print("TEST CASE 6: Payment Instruction with ING")
print("█"*80)

ocr_6 = """
Betaalopdracht

Begunstigde: Elektriciteit Bedrijf
IBAN: NL91 INGB 0002 3456 78
Bedrag: €250.00

Dank voor uw betaling via ING betaalmogelijkheid
"""

cat6, sup6, pur6, fn6 = test_case(
    "Payment Instruction",
    ocr_6,
    "betaalopdracht.pdf",
    "betaalopdracht",
)

print(f"\nEXPECTED: category=overig, supplier should NOT be ing (payment context only)")
print(f"ACTUAL: category={cat6}, supplier={sup6}, purpose={pur6}")
assert sup6 != 'ing', f"Supplier should not be ing for payment-only context, got {sup6}"


print("\n\n" + "█"*80)
print("TEST CASE 7: OCR-first Supplier Detection")
print("█"*80)

ocr_7a = """
Vitens
Termijnfactuur
Factuurnummer: 134301917070
Klantnummer: 12345678
Periode: mei 2026
"""

cat7a, sup7a, pur7a, fn7a = test_case(
    "Vitens OCR-first",
    ocr_7a,
    "termijnfactuur_134301917070.pdf",
    "Fwd: termijnfactuur 134301917070",
    sender_email='customer@gmail.com',
    date_received='2026-05-17',
)

print(f"\nEXPECTED: supplier=vitens")
print(f"ACTUAL: supplier={sup7a}, filename={fn7a}")
assert sup7a == 'vitens', f"Supplier should be vitens, got {sup7a}"
assert 'vitens' in fn7a, f"Filename should contain vitens, got {fn7a}"

ocr_7b = """
Zoho Corporation B.V.
Invoice
Invoice Number: 92953051
Total Due: EUR 29.00
"""

cat7b, sup7b, pur7b, fn7b = test_case(
    "Zoho Corporation OCR-first",
    ocr_7b,
    "invoice_92953051.pdf",
    "Fwd: Invoice 92953051",
    sender_email='customer@gmail.com',
    date_received='2026-05-17',
)

print(f"\nEXPECTED: supplier=zoho_corporation")
print(f"ACTUAL: supplier={sup7b}, filename={fn7b}")
assert sup7b == 'zoho_corporation', f"Supplier should be zoho_corporation, got {sup7b}"
assert 'zoho_corporation' in fn7b, f"Filename should contain zoho_corporation, got {fn7b}"

ocr_7c = """
Het Juridisch Loket
Adviesdocument
Datum: 17-05-2026
Onderwerp: juridisch advies
"""

cat7c, sup7c, pur7c, fn7c = test_case(
    "Het Juridisch Loket OCR-first",
    ocr_7c,
    "adviesdocument.pdf",
    "Fwd: adviesdocument",
    sender_email='customer@gmail.com',
    date_received='2026-05-17',
)

print(f"\nEXPECTED: supplier=het_juridisch_loket")
print(f"ACTUAL: supplier={sup7c}, filename={fn7c}")
assert sup7c == 'het_juridisch_loket', f"Supplier should be het_juridisch_loket, got {sup7c}"
assert 'het_juridisch_loket' in fn7c, f"Filename should contain het_juridisch_loket, got {fn7c}"

ocr_7d = """
Gemeentebelastingen Amstelland
Aanslagbiljet gemeentelijke belastingen
Dagtekening: 17-05-2026
Betreft: afvalstoffenheffing
"""

cat7d, sup7d, pur7d, fn7d = test_case(
    "Gemeentebelastingen Amstelland OCR-first",
    ocr_7d,
    "juridische_documentatie_2026.pdf",
    "Fwd: juridische documentatie",
    sender_email='customer@gmail.com',
    date_received='2026-05-17',
)

print(f"\nEXPECTED: supplier=gemeentebelastingen_amstelland")
print(f"ACTUAL: supplier={sup7d}, filename={fn7d}")
assert sup7d == 'gemeentebelastingen_amstelland', f"Supplier should be gemeentebelastingen_amstelland, got {sup7d}"
assert 'gemeentebelastingen_amstelland' in fn7d, f"Filename should contain gemeentebelastingen_amstelland, got {fn7d}"

print("\n\n" + "█"*80)
print("TEST CASE 8: Runtime document understanding")
print("█"*80)

ocr_8a = """
Advies van het Juridisch Loket
Datum: 24-02-2026
Juridisch advies
Onderwerp: alimentatie
Ons advies is gebaseerd op de door u verstrekte gegevens.
Adviesdocument
"""

cat8a, sup8a, pur8a, fn8a = test_case(
    "Het Juridisch Loket adviesdocument",
    ocr_8a,
    "adviesdocument.pdf",
    "Fwd: adviesdocument",
    sender_email='customer@gmail.com',
    date_received='2026-05-17',
)

print(f"\nEXPECTED: category=overig, purpose=juridisch_advies, filename starts juridisch_advies_het_juridisch_loket")
print(f"ACTUAL: category={cat8a}, supplier={sup8a}, purpose={pur8a}, filename={fn8a}")
assert cat8a == 'overig', f"Advice document should not be facturen, got {cat8a}"
assert pur8a in {'advies', 'juridisch_advies'}, f"Purpose should be advice, got {pur8a}"
assert fn8a == 'juridisch_advies_het_juridisch_loket_24-02-2026.pdf', f"Unexpected filename: {fn8a}"

ocr_8b = """
Zoho Corporation B.V.
INVOICE
Invoice# 92953051
Annual Subscription fee
VAT
Total
Due Date: 17-05-2026
"""

cat8b, sup8b, pur8b, fn8b = test_case(
    "Zoho subscription invoice",
    ocr_8b,
    "invoice_92953051.pdf",
    "Fwd: Invoice 92953051",
    sender_email='customer@gmail.com',
    date_received='2026-05-17',
)

print(f"\nEXPECTED: category=facturen, purpose=factuur, no bon in filename")
print(f"ACTUAL: category={cat8b}, supplier={sup8b}, purpose={pur8b}, filename={fn8b}")
assert cat8b == 'facturen', f"Zoho invoice should be facturen, got {cat8b}"
assert sup8b == 'zoho_corporation', f"Supplier should be zoho_corporation, got {sup8b}"
assert pur8b == 'factuur', f"Purpose should be factuur, got {pur8b}"
assert fn8b == 'factuur_zoho_corporation_17-05-2026.pdf', f"Unexpected filename: {fn8b}"

ocr_8c = ""

cat8c, sup8c, pur8c, fn8c = test_case(
    "Lemonade polis without OCR",
    ocr_8c,
    "document.pdf",
    "Hier is je nieuwe Lemonade polis",
    sender_email='customer@gmail.com',
    date_received='2026-05-17',
)

print(f"\nEXPECTED: supplier=lemonade, purpose=polis, filename=polis_lemonade_17-05-2026.pdf")
print(f"ACTUAL: category={cat8c}, supplier={sup8c}, purpose={pur8c}, filename={fn8c}")
assert sup8c == 'lemonade', f"Supplier should be lemonade, got {sup8c}"
assert pur8c == 'polis', f"Purpose should be polis, got {pur8c}"
assert fn8c == 'polis_lemonade_17-05-2026.pdf', f"Unexpected filename: {fn8c}"

ocr_8d = ""

cat8d, sup8d, pur8d, fn8d = test_case(
    "Kwijtscheldingsformulier gemeente belasting",
    ocr_8d,
    "Ondernemers kwijtscheldingsformulier.pdf",
    "Fwd: KWS-RK- B000198504",
    sender_email='customer@gmail.com',
    date_received='2026-05-17',
)

print(f"\nEXPECTED: category=belasting, purpose=kwijtscheldingsformulier, no fwd/random supplier")
print(f"ACTUAL: category={cat8d}, supplier={sup8d}, purpose={pur8d}, filename={fn8d}")
assert cat8d == 'belasting', f"Kwijtscheldingsformulier should be belasting, got {cat8d}"
assert sup8d not in {'fwd', 'kws', 'rk', 'b000198504', 'fwd-_kws-rk-_b000198504'}, f"Forwarded subject noise became supplier: {sup8d}"
assert pur8d == 'kwijtscheldingsformulier', f"Purpose should be kwijtscheldingsformulier, got {pur8d}"
assert fn8d == 'belasting_kwijtscheldingsformulier_17-05-2026.pdf', f"Unexpected filename: {fn8d}"

print("\n\n" + "█"*80)
ocr_8e = ""

cat8e, sup8e, pur8e, fn8e = test_case(
    "Metadata terms are not suppliers",
    ocr_8e,
    "kwijtscheldingsformulier.pdf",
    "Fwd: registratienr M2511 zaaknummer 202565138 kenmerk ABC123",
    sender_email='customer@gmail.com',
    date_received='2026-05-17',
)

print(f"\nEXPECTED: no metadata supplier terms in supplier or filename")
print(f"ACTUAL: category={cat8e}, supplier={sup8e}, purpose={pur8e}, filename={fn8e}")
assert sup8e == 'onbekend', f"Administrative metadata should not become supplier, got {sup8e}"
assert fn8e == 'belasting_kwijtscheldingsformulier_17-05-2026.pdf', f"Unexpected filename: {fn8e}"


print("\n\n" + "█"*80)
print("TEST CASE 9: Document emails without attachments")
print("█"*80)

apple_subject = "Your Apple invoice"
apple_body = """
Apple
Invoice
Invoice Number: APL-2026-0516
Date: 16-05-2026
VAT: EUR 2.10
Total: EUR 12.99
"""
apple_mail = TestMail(apple_subject, apple_body, from_email='no_reply@email.apple.com')
apple_text = f"{apple_subject}\n{apple_body}"
assert is_document_email_without_attachment(apple_mail), "Apple invoice body should be recognized as document email"
cat9a, sup9a, pur9a, fn9a = test_case(
    "Apple invoice email body",
    apple_text,
    "email_body.pdf",
    apple_subject,
    sender_email=apple_mail.from_email,
    date_received='2026-05-16',
)
assert cat9a == 'facturen', f"Apple email invoice should be facturen, got {cat9a}"
assert sup9a == 'apple', f"Supplier should be apple, got {sup9a}"
assert fn9a == 'factuur_apple_16-05-2026.pdf', f"Unexpected filename: {fn9a}"

odido_subject = "Odido betalingsherinnering"
odido_body = """
Odido
Betalingsherinnering
Factuurnummer: O-2026-1205
Totaalbedrag: EUR 48,50
IBAN: NL00BANK0123456789
Datum: 12-05-2026
"""
odido_mail = TestMail(odido_subject, odido_body, from_email='noreply@odido.nl')
odido_text = f"{odido_subject}\n{odido_body}"
assert is_document_email_without_attachment(odido_mail), "Odido payment reminder body should be recognized as document email"
cat9b, sup9b, pur9b, fn9b = test_case(
    "Odido betalingsherinnering email body",
    odido_text,
    "email_body.pdf",
    odido_subject,
    sender_email=odido_mail.from_email,
    date_received='2026-05-12',
)
assert sup9b == 'odido', f"Supplier should be odido, got {sup9b}"
assert pur9b == 'betalingsherinnering', f"Purpose should be betalingsherinnering, got {pur9b}"
assert fn9b == 'betalingsherinnering_odido_12-05-2026.pdf', f"Unexpected filename: {fn9b}"

search_mail = TestMail('Zoek mijn factuur van Apple', 'Kun je mijn Apple factuur sturen?')
assert not is_document_email_without_attachment(search_mail), "Search mail should not be treated as document email"

plain_mail = TestMail('Afspraak morgen', 'Hoi, zullen we morgen om 10:00 even bellen?')
assert not is_document_email_without_attachment(plain_mail), "Plain non-document mail should not be treated as document email"

print("✓ ALL TESTS PASSED!")
print("█"*80)
