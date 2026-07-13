"""Pipeline orchestrator — runs all gates, emits SSE events, persists result."""
from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app.config import get_settings
from app.models import Run, Submission
from app.pipeline import (
    decision,
    email_draft,
    gate1_completeness,
    gate2_extraction,
    gate3_format,
    gate4_consistency,
    gate5_credibility,
)
from app.schemas import CheckResult, RunResult, SubmissionForm
from app.services.llm import strict_json as default_strict_json

GATE_TITLES = {
    1: "Completeness",
    2: "Document extraction",
    3: "Format validation",
    4: "Cross-field consistency",
    5: "Credibility",
}

# In-memory live event fans for SSE subscribers keyed by submission_id
_subscribers: dict[str, list[asyncio.Queue]] = {}
_lock = asyncio.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(3)}"


async def subscribe(submission_id: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    async with _lock:
        _subscribers.setdefault(submission_id, []).append(queue)
    return queue


async def unsubscribe(submission_id: str, queue: asyncio.Queue) -> None:
    async with _lock:
        fans = _subscribers.get(submission_id, [])
        if queue in fans:
            fans.remove(queue)
        if not fans:
            _subscribers.pop(submission_id, None)


async def _emit(session: Session, run: Run, event: str, data: dict[str, Any]) -> None:
    payload = {"event": event, "data": data}
    events = json.loads(run.events_json or "[]")
    events.append(payload)
    run.events_json = json.dumps(events)
    session.add(run)
    session.commit()
    session.refresh(run)

    async with _lock:
        fans = list(_subscribers.get(run.submission_id, []))
    for q in fans:
        await q.put(payload)


async def run_pipeline(
    session: Session,
    submission: Submission,
    run: Run,
    *,
    strict_json: Callable[..., Awaitable[dict | None]] | None = None,
) -> RunResult:
    settings = get_settings()
    form = SubmissionForm.model_validate_json(submission.form_json)
    documents = {
        "tax_certificate": (
            Path(submission.tax_certificate_path)
            if submission.tax_certificate_path
            else None
        ),
        "bank_proof": (
            Path(submission.bank_proof_path) if submission.bank_proof_path else None
        ),
    }
    sj = strict_json or default_strict_json
    all_checks: list[CheckResult] = []
    extracted: dict[str, Any] = {}
    audit: dict[str, Any] = {
        "received_at": submission.received_at.isoformat(),
        "ruleset_version": settings.ruleset_version,
        "model": settings.sarvam_model,
        "sanctions_source": "unavailable",
    }

    await _emit(
        session,
        run,
        "run_started",
        {
            "submission_id": submission.id,
            "vendor": submission.vendor_legal_name,
            "country": submission.country,
            "ruleset_version": settings.ruleset_version,
        },
    )

    # --- Gate 1 ---
    await _emit(session, run, "gate_started", {"gate": 1, "title": GATE_TITLES[1]})
    g1 = await gate1_completeness.run(form, documents)
    for c in g1:
        all_checks.append(c)
        await _emit(session, run, "check_completed", c.model_dump())
    await _emit(session, run, "gate_completed", {"gate": 1})

    # --- Gate 2 ---
    await _emit(session, run, "gate_started", {"gate": 2, "title": GATE_TITLES[2]})
    try:
        g2, extracted = await gate2_extraction.run(documents, strict_json=sj)
    except Exception as exc:  # noqa: BLE001
        g2 = [
            CheckResult(
                check_id="gate_error__extraction",
                gate=2,
                category="extraction",
                method="llm",
                result="error",
                severity="pending_item",
                evidence=f"{type(exc).__name__}: {exc}",
            )
        ]
        extracted = {"tax_certificate": None, "bank_proof": None}
    for c in g2:
        all_checks.append(c)
        await _emit(session, run, "check_completed", c.model_dump())
    await _emit(session, run, "gate_completed", {"gate": 2})

    # --- Gate 3 ---
    await _emit(session, run, "gate_started", {"gate": 3, "title": GATE_TITLES[3]})
    try:
        g3 = await gate3_format.run(form)
    except Exception as exc:  # noqa: BLE001
        g3 = [
            CheckResult(
                check_id="gate_error__format",
                gate=3,
                category="format",
                method="deterministic",
                result="error",
                severity="pending_item",
                evidence=f"{type(exc).__name__}: {exc}",
            )
        ]
    for c in g3:
        all_checks.append(c)
        await _emit(session, run, "check_completed", c.model_dump())
    await _emit(session, run, "gate_completed", {"gate": 3})

    # --- Gate 4 ---
    await _emit(session, run, "gate_started", {"gate": 4, "title": GATE_TITLES[4]})

    async def _sj_wrapper(system: str, user: str, schema_hint, max_retries: int = 1):
        hint = schema_hint if isinstance(schema_hint, str) else json.dumps(schema_hint)
        return await sj(system, user, hint, max_retries)

    try:
        g4 = await gate4_consistency.run(
            form, extracted, strict_json=_sj_wrapper, documents=documents
        )
    except Exception as exc:  # noqa: BLE001
        g4 = [
            CheckResult(
                check_id="gate_error__consistency",
                gate=4,
                category="consistency",
                method="deterministic",
                result="error",
                severity="pending_item",
                evidence=f"{type(exc).__name__}: {exc}",
            )
        ]
    for c in g4:
        all_checks.append(c)
        await _emit(session, run, "check_completed", c.model_dump())
    await _emit(session, run, "gate_completed", {"gate": 4})

    # --- Gate 5 ---
    await _emit(session, run, "gate_started", {"gate": 5, "title": GATE_TITLES[5]})
    try:
        g5, g5_audit = await gate5_credibility.run(
            form, session, strict_json=_sj_wrapper
        )
        audit.update(g5_audit or {})
    except Exception as exc:  # noqa: BLE001
        g5 = [
            CheckResult(
                check_id="gate_error__credibility",
                gate=5,
                category="credibility",
                method="external_api",
                result="error",
                severity="pending_item",
                evidence=f"{type(exc).__name__}: {exc}",
            )
        ]
    for c in g5:
        all_checks.append(c)
        await _emit(session, run, "check_completed", c.model_dump())
    await _emit(session, run, "gate_completed", {"gate": 5})

    # --- Decision ---
    decided = decision.decide(all_checks)
    await _emit(session, run, "decision", decided.model_dump())

    email_text = None
    if decided.outcome == "pending":
        try:
            email_text = await email_draft.run(
                form, decided.outcome, decided.pending_items, strict_json=_sj_wrapper
            )
        except Exception:  # noqa: BLE001
            email_text = None
        if email_text:
            await _emit(session, run, "email_draft", {"text": email_text})

    audit["decided_at"] = _utcnow().isoformat()
    result = RunResult(
        submission_id=submission.id,
        country_profile=submission.country,
        vendor_legal_name=submission.vendor_legal_name,
        status=decided.outcome,
        checks=all_checks,
        decision=decided,
        vendor_email_draft=email_text,
        audit=audit,
        extracted=extracted,
    )

    run.status = decided.outcome
    run.result_json = result.model_dump_json()
    run.finished_at = _utcnow()
    session.add(run)
    session.commit()

    await _emit(session, run, "run_completed", {"status": decided.outcome})
    return result


def load_run_events(session: Session, submission_id: str) -> list[dict[str, Any]]:
    run = session.exec(
        select(Run).where(Run.submission_id == submission_id).order_by(Run.started_at.desc())
    ).first()
    if not run:
        return []
    return json.loads(run.events_json or "[]")
