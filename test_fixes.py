#!/usr/bin/env python3
"""Test script to validate classification and supplier detection fixes."""

from bewaarhet.classifier import classify_document
from bewaarhet.utils import detect_supplier, detect_purpose, generate_filename

def test_case(name, ocr_text, filename, subject, sender_email='test@test.com'):
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
        category, filename, ocr_text, '2025-08-13', subject, supplier, purpose
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

print(f"\nEXPECTED: category=facturen, supplier detected as huur, transformed to woningbouw in filename, purpose=aanmaning")
print(f"ACTUAL: category={cat4}, supplier={sup4}, purpose={pur4}, filename={fn4}")
# The key is the final filename should have woningbouw (transformed from huur supplier)
assert 'woningbouw' in fn4, f"Filename should contain 'woningbouw', got {fn4}"
assert 'oktober' not in fn4.lower(), f"Filename should not contain 'oktober', got {fn4}"
assert 'aanmaning' in fn4 or 'huur' in fn4, f"Filename should contain purpose (aanmaning or huur), got {fn4}"


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
