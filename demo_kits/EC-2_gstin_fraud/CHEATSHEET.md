# Valid-checksum wrong state (`EC-2`)

**Expected outcome:** `rejected`

## How to run (New submission)
1. Open `/new` (or use **Load demo kit** to prefill fields).
2. Type / confirm these form fields from `form.json`:
   - Legal name: `Kaveri Agro Supplies Private Limited`
   - Trade name: `Kaveri Agro`
   - GSTIN: `27AABCK1234L1ZM`
   - Address: `No. 42, 3rd Cross, Indiranagar`, `Bengaluru`, `Karnataka` `560038`
   - Account: `50100345678901` / IFSC `HDFC0001234`
   - Beneficiary: `Kaveri Agro Supplies Private Limited`
   - Email: `accounts@kaveriagro.in` / Phone: `+91 9988776655`
3. Upload from this folder:
   - `tax_certificate.pdf`
   - `bank_proof.pdf`
4. Submit → watch `/run/:id`.

## Match / mismatch
Form GSTIN equals cert GSTIN (valid checksum). Mismatch: address Karnataka vs GSTIN state 27; registry legal name Vertex.

## Narrate these checks
Point at gstin_state_vs_address (Karnataka vs Maharashtra 27) and name_match__registry (Kaveri vs Vertex). Naive format checks still pass.

## Stick to kit numbers
Wrong account/IFSC misses `mock_bank_directory.json` and invents extra pendings.
