# Happy path (`F0`)

**Expected outcome:** `approved`

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
   - `bank_proof.pdf`
4. Submit → watch `/run/:id`.

## Match / mismatch
All three planes align (form↔tax PDF, form↔cheque, form↔mocks).

## Narrate these checks
Expand: name_match__form_vs_tax_doc, tax_id_cross_document, name_match__pennydrop (1.00), gst_registry_status Active.

## Stick to kit numbers
Wrong account/IFSC misses `mock_bank_directory.json` and invents extra pendings.
