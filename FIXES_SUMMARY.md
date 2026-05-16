# Classification and Supplier Detection Fixes - Summary

## Issues Fixed

### A. Bank Supplier False Positives ✅
**Problem:** ING/Rabobank/ABN/bunq were matching when only mentioned in payment context
- "factuur B Nails.pdf" → `factuur_ing` (wrong: 'ing' in 'Invoice')
- "factuur WSD.pdf" → `factuur_ing` (wrong)

**Solutions Implemented:**
1. **Whole-word matching for bank names** in `detect_supplier()`
   - Added `has_whole_word_match()` helper using regex word boundaries `\b...\b`
   - Prevents 'ing' in 'Invoice' from matching 'ing' supplier keyword
   
2. **Improved bank document detection** in `is_payment_context_bank()`
   - Now checks for true bank document types: bankafschrift, rekeningafschrift, creditcardafschrift, hypotheek, lening, etc.
   - Returns `False` if document is an actual bank product (allowing it as supplier)
   - Returns `True` if only payment/IBAN context (skip as supplier)

### B. Filename Supplier Fallback ✅
**Problem:** Filenames like "factuur B Nails.pdf" weren't being extracted properly
- Month names (oktober, november) were being included as suppliers

**Solutions Implemented:**
1. **Single-letter business name support**
   - Changed filter from `len(w) > 1` to `len(w) >= 1` 
   - Allows "B Nails" → "b_nails" extraction
   - Works for abbreviations like "WSD"

2. **Month name filtering**
   - Added `is_month_name()` function detecting Dutch and English month names
   - Filters out months during filename supplier extraction
   - "huur oktober.jpg" now extracts "huur" not "huur_oktober"

3. **Generic word filtering enhancement**
   - Extended generic words list: docs, document, bijlage, bestand, attachment, factuur, invoice, bon, receipt, scan, foto, pagina, page, bericht, email

### C. Belasting Category Detection ✅
**Problem:** Belasting documents weren't classified correctly when mixed with factuur signals

**Solutions Implemented:**
1. **Strengthened belasting weights in classifier**
   - Added 'betalingsregeling', 'inkomstenbelasting', 'loonheffing' to STRONG signals
   - Added 'belastingbetaling' to MEDIUM signals

2. **Belastingdienst context boost**
   - If 'belastingdienst' + (betalingsregeling|aanslag|inkomstenbelasting|loonheffing|omzetbelasting) detected
   - Gets +5 score boost to beat facturen signals

3. **Nota rule refinement**
   - "nota" no longer favors facturen when belastingdienst context present
   - Prevents belasting documents from being misclassified as facturen

### D. Huur/Woningbouw Detection ✅
**Problem:** Housing documents were being classified incorrectly
- "huur oktober.jpg" → supplier was "huur_oktober", purpose was generic

**Solutions Implemented:**
1. **Huur → Woningbouw transformation**
   - In `generate_filename()`: if supplier == 'huur', transforms to 'woningbouw'
   - Huur becomes the purpose, not the supplier

2. **Purpose detection enhancement**
   - Aanmaning (dunning notices) now highest priority
   - Betalingsregeling next
   - Huur context requires 'huurnota' or ('huur' + 'nota'), not just filename

3. **Redundant purpose filtering**
   - Skip adding purpose='huur' when supplier='woningbouw' (they're the same)
   - Prevents filenames like "factuur_woningbouw_huur"

## Test Results

All test cases pass:
```
✓ TEST CASE 1: B Nails Invoice
  Expected: factuur_b_nails_13-08-2025.pdf
  Actual:   factuur_b_nails_13-08-2025.pdf ✓

✓ TEST CASE 2: WSD Invoice  
  Expected: factuur_wsd_20-01-2026.pdf
  Actual:   factuur_wsd_20-01-2026.pdf ✓

✓ TEST CASE 3: Belastingdienst Betalingsregeling
  Expected: category=belasting, supplier=belastingdienst, purpose=betalingsregeling
  Actual:   belasting_belastingdienst_betalingsregeling_13-08-2025.jpg ✓

✓ TEST CASE 4: Huur Oktober
  Expected: factuur_woningbouw_aanmaning (no oktober in supplier)
  Actual:   factuur_woningbouw_aanmaning_13-08-2025.jpg ✓

✓ TEST CASE 5: ING Bank Statement
  Expected: supplier=ing (true bank doc)
  Actual:   overig_ing_01-06-2025.pdf ✓

✓ TEST CASE 6: Payment Instruction with ING
  Expected: supplier NOT ing (payment context only)
  Actual:   factuur_betaalopdracht_13-08-2025.pdf ✓
```

## Files Modified

1. **bewaarhet/classifier.py**
   - Enhanced WEIGHTS for 'belasting' category
   - Added special handling for belastingdienst context
   - Refined 'nota' rule to respect belasting context

2. **bewaarhet/utils.py**
   - Added `is_month_name()` helper function
   - Enhanced `is_generic_supplier_word()` with more words
   - Improved `is_payment_context_bank()` with true bank doc detection
   - Updated `detect_supplier()` with whole-word matching for banks
   - Fixed `generate_filename()` to handle supplier transformation and filtering
   - Enhanced `detect_purpose()` with better huur/aanmaning detection

3. **bewaarhet/processor.py**
   - No changes (already integrated detect_supplier/detect_purpose)

## Validation

All files compile successfully:
```
✓ bewaarhet/utils.py
✓ bewaarhet/classifier.py
✓ bewaarhet/processor.py
```

No NameErrors or syntax issues.
