#!/usr/bin/env python3
"""Test script to validate classification and supplier detection fixes."""

from bewaarhet.classifier import classify_document
from bewaarhet.utils import detect_supplier, detect_purpose, detect_domain, generate_filename

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
    purpose = detect_purpose(ocr_text, subject)
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
print("✓ ALL TESTS PASSED!")
print("█"*80)
