"""End-to-end fixture pipeline with mocked LLM + sanctions."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.config import ROOT_DIR
from app.models import Run, Submission
from app.pipeline.runner import new_id, run_pipeline
from app.schemas import SubmissionForm


@pytest.fixture()
def session(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    async def fake_strict_json(system, user, schema_hint, max_retries=1):
        hint = schema_hint if isinstance(schema_hint, str) else json.dumps(schema_hint)
        if "GST registration" in system or "gstin" in hint:
            legal = "Meridian Trading Private Limited"
            gstin = "27AABCM1234K1ZM"
            if "Kaveri" in user or "Vertex" in user or "27AABCK" in user:
                legal = "Kaveri Agro Supplies Private Limited"
                gstin = "27AABCK1234L1ZM"
            if "Rosneft" in user:
                legal = "Rosneft Trading Private Limited"
                gstin = "27AABCR1234K1ZH"
            return {
                "legal_name": legal,
                "trade_name": "Meridian",
                "gstin": gstin,
                "address_state": "Maharashtra" if gstin.startswith("27") else "Karnataka",
                "confidence": {"legal_name": 0.95, "gstin": 0.95, "address_state": 0.9},
            }
        if "bank proof" in system.lower() or "account_holder_name" in hint:
            holder = "Meridian Trading Private Limited"
            acct = "50100234567891"
            ifsc = "HDFC0001234"
            match = re.search(r"Account Holder[:\s]+([A-Za-z .]+)", user)
            if match:
                holder = match.group(1).strip()
            match_acct = re.search(r"Account Number[:\s]+(\d+)", user)
            if match_acct:
                acct = match_acct.group(1)
            match_ifsc = re.search(r"IFSC[:\s]+([A-Z0-9]+)", user)
            if match_ifsc:
                ifsc = match_ifsc.group(1)
            return {
                "account_holder_name": holder,
                "account_number": acct,
                "ifsc": ifsc,
                "confidence": {
                    "account_holder_name": 0.95,
                    "account_number": 0.95,
                    "ifsc": 0.95,
                },
            }
        if "verdict" in hint or "same_entity" in hint:
            return {"verdict": "different_entity", "rationale": "Names differ materially"}
        if "email" in system.lower() or "subject" in hint:
            return {
                "subject": "Additional information needed",
                "body": "Please provide the requested items.",
            }
        return {}

    async def fake_screen(legal_name: str, session):
        score = 0.1
        if "Rosneft" in legal_name:
            score = 0.72
        return {
            "top_score": score,
            "top_caption": "Rosneft Oil Company" if score > 0.5 else "none",
            "datasets": ["sanctions"] if score > 0.5 else [],
            "raw": {},
            "source": "live",
        }

    monkeypatch.setattr("app.pipeline.runner.default_strict_json", fake_strict_json)
    monkeypatch.setattr("app.services.llm.strict_json", fake_strict_json)
    monkeypatch.setattr("app.pipeline.gate2_extraction.default_strict_json", fake_strict_json)
    monkeypatch.setattr("app.pipeline.gate5_credibility.default_strict_json", fake_strict_json)
    monkeypatch.setattr("app.pipeline.email_draft.default_strict_json", fake_strict_json)
    monkeypatch.setattr("app.pipeline.gate5_credibility.screen_company", fake_screen)

    with Session(engine) as s:
        yield s


def _load_fixture(name: str) -> tuple[SubmissionForm, Path | None, Path | None]:
    manifest = json.loads((ROOT_DIR / "fixtures/generated/manifest.json").read_text())
    fixture = next(f for f in manifest["fixtures"] if f["name"] == name)
    form = SubmissionForm.model_validate_json((ROOT_DIR / fixture["form_path"]).read_text())
    tax = ROOT_DIR / fixture["tax_certificate"] if fixture.get("tax_certificate") else None
    bank = ROOT_DIR / fixture["bank_proof"] if fixture.get("bank_proof") else None
    return form, tax, bank


async def _run_named(session: Session, name: str) -> dict:
    form, tax, bank = _load_fixture(name)
    sub_id = new_id("sub")
    submission = Submission(
        id=sub_id,
        form_json=form.model_dump_json(),
        country=form.country,
        vendor_legal_name=form.legal_name,
        tax_certificate_path=str(tax) if tax else None,
        bank_proof_path=str(bank) if bank else None,
    )
    run = Run(id=new_id("run"), submission_id=sub_id, status="running", events_json="[]")
    session.add(submission)
    session.add(run)
    session.commit()
    result = await run_pipeline(session, submission, run, strict_json=None)
    return result.model_dump()


@pytest.mark.asyncio
async def test_f0_approved(session):
    result = await _run_named(session, "F0")
    assert result["status"] == "approved"
    assert result["decision"]["outcome"] == "approved"


@pytest.mark.asyncio
async def test_ec2_rejected(session):
    result = await _run_named(session, "EC-2")
    assert result["status"] == "rejected"
    ids = {c["check_id"] for c in result["checks"] if c["severity"] == "hard_fail"}
    assert "gstin_state_vs_address" in ids
    assert "name_match__registry" in ids


@pytest.mark.asyncio
async def test_ec3_pending_missing_bank_proof(session):
    result = await _run_named(session, "EC-3")
    assert result["status"] == "pending"
    ids = [c["check_id"] for c in result["checks"]]
    assert "doc_present__bank_proof" in ids
    pending = result["decision"]["pending_items"]
    assert len(pending) == 1
    assert pending[0]["item"] == "doc_present__bank_proof" or "bank_proof" in pending[0]["item"]


@pytest.mark.asyncio
async def test_ec1_pending_pennydrop_band(session):
    result = await _run_named(session, "EC-1")
    assert result["status"] == "pending"
    ids = [c["check_id"] for c in result["checks"]]
    assert "name_match__pennydrop" in ids
    pending = result["decision"]["pending_items"]
    assert not all(p.get("internal_only") for p in pending)
    assert result["vendor_email_draft"] is not None


@pytest.mark.asyncio
async def test_ec4_pending_sanctions_internal(session):
    result = await _run_named(session, "EC-4")
    assert result["status"] == "pending"
    pending = result["decision"]["pending_items"]
    assert any(p.get("internal_only") for p in pending)
    assert result["vendor_email_draft"] is None
