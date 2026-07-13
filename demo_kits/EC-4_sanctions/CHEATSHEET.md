# Sanctions near-match (`EC-4`)

**Expected outcome:** `pending`

## How to run (New submission)
1. Open `/new` (or use **Load demo kit** to prefill fields).
2. Type / confirm these form fields from `form.json`:
   - Legal name: `Rosneft Trading Private Limited`
   - Trade name: `Rosneft Trading`
   - GSTIN: `27AABCR1234K1ZH`
   - Address: `Unit 8, Trade Centre, Bandra Kurla Complex`, `Mumbai`, `Maharashtra` `400051`
   - Account: `50100456789012` / IFSC `HDFC0001234`
   - Beneficiary: `Rosneft Trading Private Limited`
   - Email: `accounts@rosnefttrading.in` / Phone: `+91 9876501234`
3. Upload from this folder:
   - `tax_certificate.pdf`
   - `bank_proof.pdf`
4. Submit → watch `/run/:id`.

## Match / mismatch
Docs/bank/registry clean. Deliberate gap: legal name near-matches OpenSanctions.

## Narrate these checks
Point at sanctions_screening internal badge. No vendor email when this is the only pending item.

## Stick to kit numbers
Wrong account/IFSC misses `mock_bank_directory.json` and invents extra pendings.

## Notes
- Sanctions pending item is internal-only; do not send vendor email when this is the only pending item.
