# Missing bank proof (`EC-3`)

**Expected outcome:** `pending`

## How to run (New submission)
1. Open `/new` (or use **Load demo kit** to prefill fields).
2. Type / confirm these form fields from `form.json`:
   - Legal name: `Meridian Trading Private Limited`
   - Trade name: `Meridian`
   - GSTIN: `27AABCM1234K1ZM`
   - Address: `Plot 14, Industrial Area`, `Pune`, `Maharashtra` `411001`
   - Account: `50100234567891` / IFSC `HDFC0001234`
   - Beneficiary: `Meridian Trading Private Limited`
   - Email: `accounts@meridiantrading.in` / Phone: `+91 9876543210`
3. Upload from this folder:
   - `tax_certificate.pdf`
   - `(leave bank proof empty)`
4. Submit → watch `/run/:id`.

## Match / mismatch
Same as F0 for form + tax. Deliberate gap: no bank PDF.

## Narrate these checks
Point at doc_present__bank_proof only — single pending item + vendor email.

## Stick to kit numbers
Wrong account/IFSC misses `mock_bank_directory.json` and invents extra pendings.
