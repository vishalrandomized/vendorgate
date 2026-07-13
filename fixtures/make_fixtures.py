"""Generate VendorGate demo fixtures and synchronized mock registry data."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.validation.gstin import make_gstin  # noqa: E402
from app.validation.names import BAND_LOW, PASS_THRESHOLD, similarity  # noqa: E402


GENERATED_DIR = ROOT / "fixtures" / "generated"
DEMO_KITS_DIR = ROOT / "demo_kits"
REGISTRY_PATH = ROOT / "data" / "mock_gst_registry.json"
BANK_DIRECTORY_PATH = ROOT / "data" / "mock_bank_directory.json"

BANK_NAME = "HDFC BANK"
F0_ACCOUNT = "50100234567891"
F0_IFSC = "HDFC0001234"
EC1_ACCOUNT = "50100987654321"
EC1_IFSC = "HDFC0005678"
EC2_ACCOUNT = "50100345678901"
EC2_IFSC = "HDFC0001234"
EC4_ACCOUNT = "50100456789012"
EC4_IFSC = "HDFC0001234"

EC1_BENEFICIARY = "Meridian Enterprises"
EC1_REGISTERED = "MERIDIAN LOGISTICS"
EC1_BAND_SCORE = similarity(EC1_BENEFICIARY, EC1_REGISTERED)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_pdf(path: Path, title: str, rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    y = height - 72

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(72, y, title)
    y -= 36

    pdf.setFont("Helvetica", 11)
    for label, value in rows:
        line = f"{label}: {value}"
        pdf.drawString(72, y, line[:105])
        y -= 20

    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(
        72,
        72,
        "Digitally generated fixture for VendorGate document extraction tests.",
    )
    pdf.drawRightString(width - 72, 72, "Not a real government or bank document.")
    pdf.save()


def build_form(fixture: dict[str, Any]) -> dict[str, Any]:
    address = {
        "line1": fixture["address"]["line1"],
        "city": fixture["address"]["city"],
        "state": fixture["address"]["state"],
        "postal_code": fixture["address"]["postal_code"],
    }
    return {
        "country": "IN",
        "legal_name": fixture["legal_name"],
        "trade_name": fixture["trade_name"],
        "tax_id": fixture["gstin"],
        "address": address,
        "bank": {
            "account_number": fixture["bank"]["account_number"],
            "ifsc": fixture["bank"]["ifsc"],
            "beneficiary_name": fixture["bank"]["beneficiary_name"],
        },
        "contact": fixture["contact"],
    }


def bank_directory_key(account_number: str, ifsc: str) -> str:
    return f"{account_number.strip()}|{ifsc.strip().upper()}"


def fixture_definitions() -> list[dict[str, Any]]:
    meridian_gstin = make_gstin("27", "AABCM1234K")
    kaveri_wrong_state_gstin = make_gstin("27", "AABCK1234L")
    rosneft_gstin = make_gstin("27", "AABCR1234K")

    meridian_address = {
        "line1": "Plot 14, Industrial Area",
        "city": "Pune",
        "state": "Maharashtra",
        "postal_code": "411001",
        "country": "India",
    }
    meridian_contact = {
        "email": "accounts@meridiantrading.in",
        "phone": "+91 9876543210",
    }
    f0_bank = {
        "account_number": F0_ACCOUNT,
        "ifsc": F0_IFSC,
        "beneficiary_name": "Meridian Trading Private Limited",
    }

    if not (BAND_LOW <= EC1_BAND_SCORE < PASS_THRESHOLD):
        raise RuntimeError(
            f"EC-1 name pair must land in [{BAND_LOW}, {PASS_THRESHOLD}); "
            f"got {EC1_BAND_SCORE:.4f} for {EC1_BENEFICIARY!r} vs {EC1_REGISTERED!r}"
        )

    return [
        {
            "name": "F0",
            "title": "Happy path",
            "expected_outcome": "approved",
            "description": "Clean GST certificate, active registry entry, present bank proof, and matching mock bank directory entry.",
            "legal_name": "Meridian Trading Private Limited",
            "trade_name": "Meridian",
            "gstin": meridian_gstin,
            "address": meridian_address,
            "bank": f0_bank,
            "contact": meridian_contact,
            "registry": {
                "found": True,
                "status": "Active",
                "legal_name": "Meridian Trading Private Limited",
            },
            "bank_directory": {
                "registered_name": "MERIDIAN TRADING PRIVATE LIMITED",
                "active": True,
            },
            "expected_diagnostics": [],
        },
        {
            "name": "EC-1",
            "title": "Name mismatch ownership",
            "expected_outcome": "pending",
            "description": "Ownership uncertainty from mock bank registered name vs form beneficiary.",
            "legal_name": "Meridian Trading Private Limited",
            "trade_name": "Meridian",
            "gstin": meridian_gstin,
            "address": meridian_address,
            "bank": {
                "account_number": EC1_ACCOUNT,
                "ifsc": EC1_IFSC,
                "beneficiary_name": EC1_BENEFICIARY,
            },
            "contact": meridian_contact,
            "registry": {
                "found": True,
                "status": "Active",
                "legal_name": "Meridian Trading Private Limited",
            },
            "bank_directory": {
                "registered_name": EC1_REGISTERED,
                "active": True,
            },
            "expected_diagnostics": ["name_match__pennydrop"],
            "notes": [
                f"EC-1 beneficiary {EC1_BENEFICIARY!r} vs bank registered {EC1_REGISTERED!r} "
                f"scores {EC1_BAND_SCORE:.2f} via names.similarity, landing in the LLM band "
                f"[{BAND_LOW}, {PASS_THRESHOLD}).",
                "Expected result is PENDING after LLM adjudication because the match is different or uncertain.",
            ],
        },
        {
            "name": "EC-2",
            "title": "Valid-checksum wrong state",
            "expected_outcome": "rejected",
            "description": "GSTIN has a correct checksum but encodes Maharashtra while the vendor address is in Karnataka; registry name also differs.",
            "legal_name": "Kaveri Agro Supplies Private Limited",
            "trade_name": "Kaveri Agro",
            "gstin": kaveri_wrong_state_gstin,
            "address": {
                "line1": "No. 42, 3rd Cross, Indiranagar",
                "city": "Bengaluru",
                "state": "Karnataka",
                "postal_code": "560038",
                "country": "India",
            },
            "bank": {
                "account_number": EC2_ACCOUNT,
                "ifsc": EC2_IFSC,
                "beneficiary_name": "Kaveri Agro Supplies Private Limited",
            },
            "contact": {
                "email": "accounts@kaveriagro.in",
                "phone": "+91 9988776655",
            },
            "registry": {
                "found": True,
                "status": "Active",
                "legal_name": "Vertex Commodities Private Limited",
            },
            "bank_directory": {
                "registered_name": "KAVERI AGRO SUPPLIES PRIVATE LIMITED",
                "active": True,
            },
            "expected_diagnostics": [
                "gstin_state_vs_address",
                "registry_name_match",
            ],
        },
        {
            "name": "EC-3",
            "title": "Missing bank proof",
            "expected_outcome": "pending",
            "description": "Same clean company and bank data as F0, but bank proof is intentionally absent.",
            "legal_name": "Meridian Trading Private Limited",
            "trade_name": "Meridian",
            "gstin": meridian_gstin,
            "address": meridian_address,
            "bank": f0_bank,
            "contact": meridian_contact,
            "registry": {
                "found": True,
                "status": "Active",
                "legal_name": "Meridian Trading Private Limited",
            },
            "bank_directory": {
                "registered_name": "MERIDIAN TRADING PRIVATE LIMITED",
                "active": True,
            },
            "expected_diagnostics": ["doc_present__bank_proof"],
            "omit_bank_proof": True,
        },
        {
            "name": "EC-4",
            "title": "Sanctions near-match",
            "expected_outcome": "pending",
            "description": "Clean fixture except for an internal-only sanctions near-match on the legal name.",
            "legal_name": "Rosneft Trading Private Limited",
            "trade_name": "Rosneft Trading",
            "gstin": rosneft_gstin,
            "address": {
                "line1": "Unit 8, Trade Centre, Bandra Kurla Complex",
                "city": "Mumbai",
                "state": "Maharashtra",
                "postal_code": "400051",
                "country": "India",
            },
            "bank": {
                "account_number": EC4_ACCOUNT,
                "ifsc": EC4_IFSC,
                "beneficiary_name": "Rosneft Trading Private Limited",
            },
            "contact": {
                "email": "accounts@rosnefttrading.in",
                "phone": "+91 9876501234",
            },
            "registry": {
                "found": True,
                "status": "Active",
                "legal_name": "Rosneft Trading Private Limited",
            },
            "bank_directory": {
                "registered_name": "ROSNEFT TRADING PRIVATE LIMITED",
                "active": True,
            },
            "expected_diagnostics": ["sanctions_near_match"],
            "notes": [
                "Sanctions pending item is internal-only; do not send vendor email when this is the only pending item.",
            ],
        },
    ]


def certificate_rows(fixture: dict[str, Any]) -> list[tuple[str, str]]:
    address = fixture["address"]
    address_text = (
        f"{address['line1']}, {address['city']}, {address['state']} "
        f"{address['postal_code']}, {address['country']}"
    )
    return [
        ("Legal Name", fixture["legal_name"]),
        ("Trade Name", fixture["trade_name"]),
        ("GSTIN", fixture["gstin"]),
        ("Address", address_text),
        ("State", address["state"]),
        ("Registration Status", fixture["registry"]["status"]),
    ]


def bank_rows(fixture: dict[str, Any]) -> list[tuple[str, str]]:
    bank = fixture["bank"]
    return [
        ("Account Holder", bank["beneficiary_name"]),
        ("Account Number", bank["account_number"]),
        ("IFSC", bank["ifsc"]),
        ("Bank Name", BANK_NAME),
        ("Cheque Status", "Cancelled for account verification only"),
    ]


def kit_folder_name(fixture_name: str) -> str:
    return {
        "F0": "F0_happy",
        "EC-1": "EC-1_ownership",
        "EC-2": "EC-2_gstin_fraud",
        "EC-3": "EC-3_missing_bank",
        "EC-4": "EC-4_sanctions",
    }[fixture_name]


def cheatsheet_for(fixture: dict[str, Any], form: dict[str, Any]) -> str:
    name = fixture["name"]
    bank = form["bank"]
    address = form["address"]
    uploads = ["tax_certificate.pdf"]
    if not fixture.get("omit_bank_proof"):
        uploads.append("bank_proof.pdf")
    else:
        uploads.append("(leave bank proof empty)")

    narrate = {
        "F0": (
            "Expand: name_match__form_vs_tax_doc, tax_id_cross_document, "
            "name_match__pennydrop (1.00), gst_registry_status Active."
        ),
        "EC-1": (
            "Point at name_match__pennydrop (Meridian Enterprises vs MERIDIAN LOGISTICS ~0.63) "
            "+ LLM rationale + vendor email draft."
        ),
        "EC-2": (
            "Point at gstin_state_vs_address (Karnataka vs Maharashtra 27) and "
            "name_match__registry (Kaveri vs Vertex). Naive format checks still pass."
        ),
        "EC-3": (
            "Point at doc_present__bank_proof only — single pending item + vendor email."
        ),
        "EC-4": (
            "Point at sanctions_screening internal badge. No vendor email when this is the only pending item."
        ),
    }[name]

    matches = {
        "F0": "All three planes align (form↔tax PDF, form↔cheque, form↔mocks).",
        "EC-1": "Form↔cert clean; form↔cheque both Meridian Enterprises. Mismatch: beneficiary vs mock bank MERIDIAN LOGISTICS.",
        "EC-2": "Form GSTIN equals cert GSTIN (valid checksum). Mismatch: address Karnataka vs GSTIN state 27; registry legal name Vertex.",
        "EC-3": "Same as F0 for form + tax. Deliberate gap: no bank PDF.",
        "EC-4": "Docs/bank/registry clean. Deliberate gap: legal name near-matches OpenSanctions.",
    }[name]

    lines = [
        f"# {fixture['title']} (`{name}`)",
        "",
        f"**Expected outcome:** `{fixture['expected_outcome']}`",
        "",
        "## How to run (New submission)",
        "1. Open `/new` (or use **Load demo kit** to prefill fields).",
        "2. Type / confirm these form fields from `form.json`:",
        f"   - Legal name: `{form['legal_name']}`",
        f"   - Trade name: `{form.get('trade_name') or ''}`",
        f"   - GSTIN: `{form['tax_id']}`",
        f"   - Address: `{address['line1']}`, `{address['city']}`, `{address['state']}` `{address['postal_code']}`",
        f"   - Account: `{bank['account_number']}` / IFSC `{bank['ifsc']}`",
        f"   - Beneficiary: `{bank['beneficiary_name']}`",
        f"   - Email: `{form['contact']['email']}` / Phone: `{form['contact']['phone']}`",
        "3. Upload from this folder:",
        *[f"   - `{u}`" for u in uploads],
        "4. Submit → watch `/run/:id`.",
        "",
        "## Match / mismatch",
        matches,
        "",
        "## Narrate these checks",
        narrate,
        "",
        "## Stick to kit numbers",
        "Wrong account/IFSC misses `mock_bank_directory.json` and invents extra pendings.",
        "",
    ]
    if fixture.get("notes"):
        lines.append("## Notes")
        for note in fixture["notes"]:
            lines.append(f"- {note}")
        lines.append("")
    return "\n".join(lines)


def write_demo_kits(manifest_entries: list[dict[str, Any]], fixtures: list[dict[str, Any]]) -> None:
    if DEMO_KITS_DIR.exists():
        shutil.rmtree(DEMO_KITS_DIR)
    DEMO_KITS_DIR.mkdir(parents=True, exist_ok=True)

    by_name = {f["name"]: f for f in fixtures}
    kit_index = []

    for entry in manifest_entries:
        fixture = by_name[entry["name"]]
        folder = DEMO_KITS_DIR / kit_folder_name(entry["name"])
        folder.mkdir(parents=True, exist_ok=True)

        form_src = ROOT / entry["form_path"]
        form = json.loads(form_src.read_text())
        shutil.copy2(form_src, folder / "form.json")
        shutil.copy2(ROOT / entry["tax_certificate"], folder / "tax_certificate.pdf")
        if entry.get("bank_proof"):
            shutil.copy2(ROOT / entry["bank_proof"], folder / "bank_proof.pdf")

        (folder / "CHEATSHEET.md").write_text(cheatsheet_for(fixture, form))
        kit_index.append(
            {
                "id": kit_folder_name(entry["name"]),
                "fixture": entry["name"],
                "title": entry["title"],
                "expected_outcome": entry["expected_outcome"],
                "description": entry["description"],
                "has_bank_proof": bool(entry.get("bank_proof")),
                "path": rel(folder),
            }
        )

    write_json(DEMO_KITS_DIR / "index.json", {"kits": kit_index})
    readme = """# Demo kits — New Submission walkthrough

Each folder is a complete manual upload pack:

1. Open `CHEATSHEET.md`
2. Prefill via `/new` → **Load demo kit**, or type from `form.json`
3. Drop the PDFs from that same folder
4. Submit and narrate match/mismatch on the run view

Regenerated by `python fixtures/make_fixtures.py`.
"""
    (DEMO_KITS_DIR / "README.md").write_text(readme)


def generate() -> None:
    if GENERATED_DIR.exists():
        shutil.rmtree(GENERATED_DIR)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    definitions = fixture_definitions()
    manifest_entries = []
    registry = {}
    bank_directory = {}

    for fixture in definitions:
        fixture_dir = GENERATED_DIR / fixture["name"]
        form_path = fixture_dir / "form.json"
        tax_certificate_path = fixture_dir / "tax_certificate.pdf"
        bank_proof_path = fixture_dir / "bank_proof.pdf"

        write_json(form_path, build_form(fixture))
        write_pdf(
            tax_certificate_path,
            "GST REGISTRATION CERTIFICATE",
            certificate_rows(fixture),
        )
        if not fixture.get("omit_bank_proof"):
            write_pdf(bank_proof_path, "CANCELLED CHEQUE", bank_rows(fixture))

        registry[fixture["gstin"]] = fixture["registry"]
        bank = fixture["bank"]
        bank_directory[bank_directory_key(bank["account_number"], bank["ifsc"])] = fixture[
            "bank_directory"
        ]

        manifest_entry = {
            "name": fixture["name"],
            "title": fixture["title"],
            "expected_outcome": fixture["expected_outcome"],
            "description": fixture["description"],
            "gstin": fixture["gstin"],
            "expected_diagnostics": fixture["expected_diagnostics"],
            "form_path": rel(form_path),
            "tax_certificate": rel(tax_certificate_path),
        }
        if not fixture.get("omit_bank_proof"):
            manifest_entry["bank_proof"] = rel(bank_proof_path)
        if fixture.get("notes"):
            manifest_entry["notes"] = fixture["notes"]

        manifest_entries.append(manifest_entry)

    write_json(GENERATED_DIR / "manifest.json", {"fixtures": manifest_entries})
    write_json(REGISTRY_PATH, registry)
    write_json(BANK_DIRECTORY_PATH, bank_directory)
    write_demo_kits(manifest_entries, definitions)


if __name__ == "__main__":
    generate()
    print(f"Generated fixtures in {rel(GENERATED_DIR)}")
    print(f"Wrote demo kits to {rel(DEMO_KITS_DIR)}")
    print(f"Wrote registry to {rel(REGISTRY_PATH)}")
    print(f"Wrote bank directory to {rel(BANK_DIRECTORY_PATH)}")
    print(f"EC-1 similarity score: {EC1_BAND_SCORE:.4f}")
