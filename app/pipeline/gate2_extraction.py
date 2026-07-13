"""Gate 2: pdfplumber text extraction → Sarvam 105B structured fields."""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pdfplumber

from app.pipeline.helpers import make_check, timed
from app.schemas import CheckResult, PendingItem
from app.services.llm import strict_json as default_strict_json

StrictJson = Callable[..., Awaitable[dict | None]]

CONFIDENCE_FLOOR = 0.7

TAX_SYSTEM = (
    "You extract fields from Indian GST registration certificates. "
    "Respond with a single raw JSON object. No markdown fences, no preamble, no trailing text."
)
TAX_SCHEMA = (
    '{"legal_name": str|null, "trade_name": str|null, "gstin": str|null, '
    '"address_state": str|null, "confidence": {"legal_name": 0-1, "gstin": 0-1, "address_state": 0-1}}'
)

BANK_SYSTEM = (
    "You extract fields from Indian bank proofs (cancelled cheques / statements). "
    "Respond with a single raw JSON object. No markdown fences, no preamble, no trailing text."
)
BANK_SCHEMA = (
    '{"account_holder_name": str|null, "account_number": str|null, "ifsc": str|null, '
    '"confidence": {"account_holder_name": 0-1, "account_number": 0-1, "ifsc": 0-1}}'
)


def _pending(item: str, detail: str, action_required: str) -> PendingItem:
    return PendingItem(item=item, detail=detail, action_required=action_required)


def extract_pdf_text(path: Path) -> str:
    chunks: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(text)
    return "\n".join(chunks).strip()


def _coerce_confidence(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


async def _extract_one(
    *,
    doc_key: str,
    path: Path | None,
    system: str,
    schema: str,
    fields: list[str],
    strict_json_func: StrictJson,
) -> tuple[list[CheckResult], dict[str, Any] | None]:
    checks: list[CheckResult] = []

    if path is None or not path.exists():
        # Gate 1 already flags missing docs; Gate 2 skips quietly.
        return checks, None

    with timed() as duration:
        try:
            text = extract_pdf_text(path)
        except Exception as exc:  # noqa: BLE001
            checks.append(
                make_check(
                    check_id=f"doc_readable__{doc_key}",
                    gate=2,
                    category="extraction",
                    method="deterministic",
                    result="error",
                    severity="pending_item",
                    evidence=f"{type(exc).__name__}: {exc}",
                    duration_ms=duration[0],
                    pending_item=_pending(
                        f"doc_readable__{doc_key}",
                        f"Failed to open {doc_key}",
                        f"Re-upload a valid PDF for {doc_key.replace('_', ' ')}",
                    ),
                )
            )
            return checks, None

    if len(text.strip()) < 50:
        checks.append(
            make_check(
                check_id=f"doc_readable__{doc_key}",
                gate=2,
                category="extraction",
                method="deterministic",
                result="fail",
                severity="pending_item",
                evidence=f"Extracted {len(text.strip())} chars (<50); document unreadable",
                duration_ms=duration[0],
                pending_item=_pending(
                    f"doc_readable__{doc_key}",
                    "document unreadable, please re-upload",
                    f"Re-upload a clearer PDF for {doc_key.replace('_', ' ')}",
                ),
            )
        )
        return checks, None

    checks.append(
        make_check(
            check_id=f"doc_readable__{doc_key}",
            gate=2,
            category="extraction",
            method="deterministic",
            result="pass",
            severity="pass",
            evidence=f"Extracted {len(text)} characters from {doc_key}",
            duration_ms=duration[0],
        )
    )

    user = (
        f"Document text:\n<<<{text}>>>\n"
        f"Extract: {schema}\n"
        "Use null for anything not present. Confidence reflects how certain you are "
        "the value is transcribed exactly as printed."
    )

    with timed() as llm_duration:
        try:
            payload = await strict_json_func(system, user, schema, 1)
        except Exception as exc:  # noqa: BLE001
            payload = None
            err = f"{type(exc).__name__}: {exc}"
        else:
            err = None

    if payload is None:
        checks.append(
            make_check(
                check_id=f"extraction__{doc_key}",
                gate=2,
                category="extraction",
                method="llm",
                result="error",
                severity="pending_item",
                evidence=err or "LLM returned unparseable JSON after retry",
                duration_ms=llm_duration[0],
                pending_item=_pending(
                    f"extraction__{doc_key}",
                    "Could not extract structured fields",
                    f"Re-upload a clearer copy of {doc_key.replace('_', ' ')}",
                ),
            )
        )
        return checks, None

    confidence = _coerce_confidence(payload.get("confidence"))
    cleaned: dict[str, Any] = dict(payload)
    cleaned["confidence"] = confidence

    for field in fields:
        conf = confidence.get(field)
        value = payload.get(field)
        if conf is None or conf < CONFIDENCE_FLOOR or value in (None, ""):
            cleaned[field] = None
            checks.append(
                make_check(
                    check_id=f"extraction_confidence__{doc_key}__{field}",
                    gate=2,
                    category="extraction",
                    method="llm",
                    result="warn",
                    severity="pending_item",
                    evidence=(
                        f"confidence={conf!r} value={value!r}; "
                        f"could not reliably read {field} from {doc_key}"
                    ),
                    duration_ms=llm_duration[0],
                    pending_item=_pending(
                        f"extraction_confidence__{doc_key}__{field}",
                        f"Low confidence on {field}",
                        f"Please re-upload a clearer copy of {doc_key.replace('_', ' ')}",
                    ),
                )
            )
        else:
            checks.append(
                make_check(
                    check_id=f"extraction_confidence__{doc_key}__{field}",
                    gate=2,
                    category="extraction",
                    method="llm",
                    result="pass",
                    severity="pass",
                    evidence=f"{field}={value!r} confidence={conf:.2f}",
                    duration_ms=llm_duration[0],
                )
            )

    return checks, cleaned


async def run(
    documents: dict[str, Path | None],
    strict_json: StrictJson | None = None,
) -> tuple[list[CheckResult], dict[str, dict[str, Any] | None]]:
    """Extract structured fields from uploaded PDFs.

    Returns (checks, extracted) where extracted maps doc key → fields or None
    when the document is unavailable for downstream gates.
    """
    fn = strict_json or default_strict_json
    checks: list[CheckResult] = []
    extracted: dict[str, dict[str, Any] | None] = {
        "tax_certificate": None,
        "bank_proof": None,
    }

    tax_checks, tax_data = await _extract_one(
        doc_key="tax_certificate",
        path=documents.get("tax_certificate"),
        system=TAX_SYSTEM,
        schema=TAX_SCHEMA,
        fields=["legal_name", "gstin", "address_state"],
        strict_json_func=fn,
    )
    checks.extend(tax_checks)
    extracted["tax_certificate"] = tax_data

    bank_checks, bank_data = await _extract_one(
        doc_key="bank_proof",
        path=documents.get("bank_proof"),
        system=BANK_SYSTEM,
        schema=BANK_SCHEMA,
        fields=["account_holder_name", "account_number", "ifsc"],
        strict_json_func=fn,
    )
    checks.extend(bank_checks)
    extracted["bank_proof"] = bank_data

    return checks, extracted
