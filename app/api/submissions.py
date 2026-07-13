"""REST + SSE endpoints for submissions and fixtures."""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
from sse_starlette.sse import EventSourceResponse

from app.config import ROOT_DIR, get_settings
from app.db import get_engine
from app.models import Run, Submission
from app.pipeline.runner import (
    load_run_events,
    new_id,
    run_pipeline,
    subscribe,
    unsubscribe,
)
from app.schemas import FixtureInfo, SubmissionForm, SubmissionListItem, DemoKitInfo

router = APIRouter(prefix="/api")


def _save_upload(dest: Path, upload: UploadFile | None) -> str | None:
    if upload is None:
        return None
    filename = upload.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail=f"{filename} must be a PDF")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return str(dest)


async def _start_pipeline(submission_id: str) -> None:
    with Session(get_engine()) as session:
        submission = session.get(Submission, submission_id)
        if not submission:
            return
        run = session.exec(
            select(Run)
            .where(Run.submission_id == submission_id)
            .order_by(Run.started_at.desc())
        ).first()
        if not run:
            return
        await run_pipeline(session, submission, run)


@router.post("/submissions")
async def create_submission(
    background_tasks: BackgroundTasks,
    form: str = Form(...),
    tax_certificate: UploadFile | None = File(None),
    bank_proof: UploadFile | None = File(None),
):
    try:
        form_data = SubmissionForm.model_validate_json(form)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Malformed form JSON: {exc}") from exc

    settings = get_settings()
    submission_id = new_id("sub")
    upload_dir = settings.uploads_dir / submission_id

    tax_path = _save_upload(upload_dir / "tax_certificate.pdf", tax_certificate)
    bank_path = _save_upload(upload_dir / "bank_proof.pdf", bank_proof)

    with Session(get_engine()) as session:
        submission = Submission(
            id=submission_id,
            form_json=form_data.model_dump_json(),
            country=form_data.country or "IN",
            vendor_legal_name=form_data.legal_name,
            tax_certificate_path=tax_path,
            bank_proof_path=bank_path,
        )
        run = Run(
            id=new_id("run"),
            submission_id=submission_id,
            status="running",
            events_json="[]",
        )
        session.add(submission)
        session.add(run)
        session.commit()

    background_tasks.add_task(_start_pipeline, submission_id)
    return {"submission_id": submission_id, "id": submission_id}


@router.get("/submissions")
def list_submissions() -> list[SubmissionListItem]:
    with Session(get_engine()) as session:
        rows = session.exec(select(Submission).order_by(Submission.received_at.desc())).all()
        items: list[SubmissionListItem] = []
        for sub in rows:
            run = session.exec(
                select(Run)
                .where(Run.submission_id == sub.id)
                .order_by(Run.started_at.desc())
            ).first()
            hard = pending = flags = 0
            decided_at = None
            status = run.status if run else "error"
            if run and run.result_json:
                result = json.loads(run.result_json)
                decision = result.get("decision") or {}
                hard = len(decision.get("hard_fails") or [])
                pending = len(decision.get("pending_items") or [])
                flags = len(decision.get("soft_flags") or [])
                decided_at = run.finished_at
            items.append(
                SubmissionListItem(
                    id=sub.id,
                    vendor_legal_name=sub.vendor_legal_name,
                    country=sub.country,
                    status=status,
                    hard_fail_count=hard,
                    pending_count=pending,
                    flag_count=flags,
                    received_at=sub.received_at,
                    decided_at=decided_at,
                )
            )
        return items


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: str):
    with Session(get_engine()) as session:
        submission = session.get(Submission, submission_id)
        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")
        run = session.exec(
            select(Run)
            .where(Run.submission_id == submission_id)
            .order_by(Run.started_at.desc())
        ).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if run.result_json:
            return json.loads(run.result_json)
        return {
            "submission_id": submission_id,
            "country_profile": submission.country,
            "vendor_legal_name": submission.vendor_legal_name,
            "status": run.status,
            "checks": [],
            "decision": None,
            "vendor_email_draft": None,
            "audit": {},
            "events": json.loads(run.events_json or "[]"),
        }


@router.get("/submissions/{submission_id}/stream")
async def stream_submission(submission_id: str):
    with Session(get_engine()) as session:
        submission = session.get(Submission, submission_id)
        if not submission:
            raise HTTPException(status_code=404, detail="Submission not found")
        existing = load_run_events(session, submission_id)
        run = session.exec(
            select(Run)
            .where(Run.submission_id == submission_id)
            .order_by(Run.started_at.desc())
        ).first()
        finished = bool(run and run.finished_at)

    queue = await subscribe(submission_id)

    async def event_generator():
        try:
            for item in existing:
                yield {
                    "event": item["event"],
                    "data": json.dumps(item["data"]),
                }
            if finished:
                return
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {
                    "event": item["event"],
                    "data": json.dumps(item["data"]),
                }
                if item["event"] == "run_completed":
                    break
        finally:
            await unsubscribe(submission_id, queue)

    return EventSourceResponse(event_generator())


def _load_manifest() -> list[dict]:
    path = ROOT_DIR / "fixtures" / "generated" / "manifest.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())["fixtures"]


@router.get("/fixtures")
def list_fixtures() -> list[FixtureInfo]:
    return [
        FixtureInfo(
            name=f["name"],
            title=f["title"],
            expected_outcome=f["expected_outcome"],
            description=f.get("description", ""),
        )
        for f in _load_manifest()
    ]


@router.post("/fixtures/{name}/run")
async def run_fixture(name: str, background_tasks: BackgroundTasks):
    fixtures = {f["name"]: f for f in _load_manifest()}
    fixture = fixtures.get(name)
    if not fixture:
        raise HTTPException(status_code=404, detail=f"Unknown fixture {name}")

    form_path = ROOT_DIR / fixture["form_path"]
    form_data = SubmissionForm.model_validate_json(form_path.read_text())

    settings = get_settings()
    submission_id = new_id("sub")
    upload_dir = settings.uploads_dir / submission_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    tax_src = fixture.get("tax_certificate")
    bank_src = fixture.get("bank_proof")
    tax_path = None
    bank_path = None
    if tax_src:
        dest = upload_dir / "tax_certificate.pdf"
        shutil.copy2(ROOT_DIR / tax_src, dest)
        tax_path = str(dest)
    if bank_src:
        dest = upload_dir / "bank_proof.pdf"
        shutil.copy2(ROOT_DIR / bank_src, dest)
        bank_path = str(dest)

    with Session(get_engine()) as session:
        submission = Submission(
            id=submission_id,
            form_json=form_data.model_dump_json(),
            country=form_data.country or "IN",
            vendor_legal_name=form_data.legal_name,
            tax_certificate_path=tax_path,
            bank_proof_path=bank_path,
        )
        run = Run(
            id=new_id("run"),
            submission_id=submission_id,
            status="running",
            events_json="[]",
        )
        session.add(submission)
        session.add(run)
        session.commit()

    background_tasks.add_task(_start_pipeline, submission_id)
    return {"submission_id": submission_id, "id": submission_id}


def _load_demo_kits_index() -> list[dict]:
    path = ROOT_DIR / "demo_kits" / "index.json"
    if not path.exists():
        return []
    return json.loads(path.read_text()).get("kits") or []


def _demo_kit_dir(kit_id: str) -> Path:
    kits = {k["id"]: k for k in _load_demo_kits_index()}
    kit = kits.get(kit_id)
    if not kit:
        raise HTTPException(status_code=404, detail=f"Unknown demo kit {kit_id}")
    folder = ROOT_DIR / kit["path"]
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail=f"Demo kit folder missing: {kit_id}")
    return folder


@router.get("/demo-kits")
def list_demo_kits() -> list[DemoKitInfo]:
    return [DemoKitInfo.model_validate(k) for k in _load_demo_kits_index()]


@router.get("/demo-kits/{kit_id}/form")
def get_demo_kit_form(kit_id: str):
    form_path = _demo_kit_dir(kit_id) / "form.json"
    if not form_path.exists():
        raise HTTPException(status_code=404, detail="form.json missing for kit")
    return json.loads(form_path.read_text())
