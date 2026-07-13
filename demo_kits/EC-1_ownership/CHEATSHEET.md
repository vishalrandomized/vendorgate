# Name mismatch ownership (`EC-1`)

**Expected outcome:** `pending`

## How to run (New submission)
1. Open `/new` (or use **Load demo kit** to prefill fields).
2. Type / confirm these form fields from `form.json`:
   - Legal name: `Meridian Trading Private Limited`
   - Trade name: `Meridian`
   - GSTIN: `27AABCM1234K1ZM`
   - Address: `Plot 14, Industrial Area`, `Pune`, `Maharashtra` `411001`
   - Account: `50100987654321` / IFSC `HDFC0005678`
   - Beneficiary: `Meridian Enterprises`
   - Email: `accounts@meridiantrading.in` / Phone: `+91 9876543210`
3. Upload from this folder:
   - `tax_certificate.pdf`
   - `bank_proof.pdf`
4. Submit → watch `/run/:id`.

## Match / mismatch
Form↔cert clean; form↔cheque both Meridian Enterprises. Mismatch: beneficiary vs mock bank MERIDIAN LOGISTICS.

## Narrate these checks
Point at name_match__pennydrop (Meridian Enterprises vs MERIDIAN LOGISTICS ~0.63) + LLM rationale + vendor email draft.

## Stick to kit numbers
Wrong account/IFSC misses `mock_bank_directory.json` and invents extra pendings.

## Notes
- EC-1 beneficiary 'Meridian Enterprises' vs bank registered 'MERIDIAN LOGISTICS' scores 0.63 via names.similarity, landing in the LLM band [0.6, 0.85).
- Expected result is PENDING after LLM adjudication because the match is different or uncertain.
