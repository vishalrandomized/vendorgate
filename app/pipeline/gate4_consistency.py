"""Gate 4: deterministic and assisted consistency checks."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.pipeline.helpers import make_check
from app.profiles import STATE_ALIASES
from app.schemas import CheckResult, PendingItem, SubmissionForm
from app.validation.gstin import decode_state
from app.validation.names import BAND_LOW, PASS_THRESHOLD, similarity

StrictJson = Callable[[str, str, Any], Awaitable[dict[str, Any]]]


def _pending(item: str, detail: str, action_required: str) -> PendingItem:
    return PendingItem(item=item, detail=detail, action_required=action_required)


def _extract_string(data: dict[str, Any] | None, *keys: str) -> str:
    if not data:
        return ""
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _normalized_id(value: str | None) -> str:
    return (value or "").strip().upper()


def _canonical_state(value: str | None) -> str:
    normalized = " ".join((value or "").strip().lower().split())
    return STATE_ALIASES.get(normalized, normalized)


def _missing_doc_name_check(check_id: str) -> CheckResult:
    """Doc absent — Gate 1 already owns the pending item; do not double-count."""
    return make_check(
        check_id=check_id,
        gate=4,
        category="consistency",
        method="deterministic",
        result="skipped",
        severity="pass",
        evidence="blocked by missing document (see completeness)",
    )


def _unreadable_name_check(check_id: str, item: str) -> CheckResult:
    return make_check(
        check_id=check_id,
        gate=4,
        category="consistency",
        method="deterministic",
        result="skipped",
        severity="pending_item",
        evidence="blocked by unreadable document",
        pending_item=_pending(
            item,
            "Document could not be read for name comparison",
            "Provide a readable document or confirm the vendor name",
        ),
    )


async def _run_name_match(
    *,
    check_id: str,
    source_name: str,
    extracted_name: str,
    missing_item: str,
    strict_json: StrictJson | None,
    doc_missing: bool = False,
) -> list[CheckResult]:
    if doc_missing:
        return [_missing_doc_name_check(check_id)]
    if not extracted_name:
        return [_unreadable_name_check(check_id, missing_item)]

    score = similarity(source_name, extracted_name)
    evidence = (
        f"Name similarity score {score:.2f}: "
        f"{source_name!r} vs {extracted_name!r}"
    )

    if score >= PASS_THRESHOLD:
        return [
            make_check(
                check_id=check_id,
                gate=4,
                category="consistency",
                method="deterministic",
                result="pass",
                severity="pass",
                evidence=evidence,
            )
        ]

    if score < BAND_LOW:
        return [
            make_check(
                check_id=check_id,
                gate=4,
                category="consistency",
                method="deterministic",
                result="fail",
                severity="hard_fail",
                evidence=evidence,
            )
        ]

    system = (
        "You adjudicate whether two vendor names refer to the same legal entity. "
        "If the distinctive business words differ (e.g. Enterprises vs Logistics, "
        "Exports, or Trading), return different_entity or uncertain — do not treat "
        "a shared first token alone as same_entity. "
        "Return strict JSON only."
    )
    user = (
        f"Compare these names:\n"
        f"Form name: {source_name}\n"
        f"Document name: {extracted_name}\n"
        f"Similarity score: {score:.2f}"
    )
    schema_hint = {
        "verdict": "same_entity | different_entity | uncertain",
        "rationale": "short explanation",
    }

    try:
        adjudication = await strict_json(system, user, schema_hint) if strict_json else {}
        verdict = str(adjudication.get("verdict", "uncertain")).strip()
        rationale = str(adjudication.get("rationale", "")).strip()
    except Exception as exc:
        verdict = "uncertain"
        rationale = f"LLM adjudication failed: {exc}"

    if verdict == "same_entity":
        return [
            make_check(
                check_id=check_id,
                gate=4,
                category="consistency",
                method="llm",
                result="pass",
                severity="pass",
                evidence=evidence,
                llm_rationale=rationale,
            ),
            make_check(
                check_id="name_match_llm_assisted",
                gate=4,
                category="consistency",
                method="llm",
                result="warn",
                severity="soft_flag",
                evidence=f"LLM assisted medium-band name match for {check_id}",
                llm_rationale=rationale,
            ),
        ]

    return [
        make_check(
            check_id=check_id,
            gate=4,
            category="consistency",
            method="llm" if strict_json else "deterministic",
            result="warn",
            severity="pending_item",
            evidence=f"{evidence}; LLM verdict: {verdict}",
            llm_rationale=rationale or None,
            pending_item=_pending(
                missing_item,
                "Vendor name could not be confidently matched",
                "Confirm the vendor name or provide supporting documentation",
            ),
        )
    ]


async def run(
    form: SubmissionForm,
    extracted: dict[str, dict[str, Any] | None],
    strict_json: StrictJson | None = None,
    documents: dict[str, Any] | None = None,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    documents = documents or {}
    tax_certificate = extracted.get("tax_certificate")
    bank_proof = extracted.get("bank_proof")
    tax_missing = documents.get("tax_certificate") is None
    bank_missing = documents.get("bank_proof") is None

    checks.extend(
        await _run_name_match(
            check_id="name_match__form_vs_tax_doc",
            source_name=form.legal_name,
            extracted_name=_extract_string(tax_certificate, "legal_name"),
            missing_item="tax_certificate",
            strict_json=strict_json,
            doc_missing=tax_missing,
        )
    )
    checks.extend(
        await _run_name_match(
            check_id="name_match__form_vs_bank_proof",
            source_name=form.bank.beneficiary_name,
            extracted_name=_extract_string(
                bank_proof, "holder", "holder_name", "account_holder_name", "beneficiary_name"
            ),
            missing_item="bank_proof",
            strict_json=strict_json,
            doc_missing=bank_missing,
        )
    )

    form_gstin = _normalized_id(form.tax_id)
    cert_gstin = _normalized_id(_extract_string(tax_certificate, "gstin", "tax_id"))
    if tax_missing:
        checks.append(
            make_check(
                check_id="tax_id_cross_document",
                gate=4,
                category="consistency",
                method="deterministic",
                result="skipped",
                severity="pass",
                evidence="blocked by missing document (see completeness)",
            )
        )
    elif not cert_gstin:
        checks.append(
            make_check(
                check_id="tax_id_cross_document",
                gate=4,
                category="consistency",
                method="deterministic",
                result="skipped",
                severity="pending_item",
                evidence="blocked by unreadable document",
                pending_item=_pending(
                    "tax_certificate",
                    "GSTIN could not be read from tax certificate",
                    "Provide a readable tax certificate",
                ),
            )
        )
    elif form_gstin == cert_gstin:
        checks.append(
            make_check(
                check_id="tax_id_cross_document",
                gate=4,
                category="consistency",
                method="deterministic",
                result="pass",
                severity="pass",
                evidence="Form GSTIN exactly matches tax certificate GSTIN",
            )
        )
    else:
        checks.append(
            make_check(
                check_id="tax_id_cross_document",
                gate=4,
                category="consistency",
                method="deterministic",
                result="fail",
                severity="hard_fail",
                evidence="Form GSTIN does not match tax certificate GSTIN",
            )
        )

    decoded_state = decode_state(form_gstin)
    if tax_missing:
        checks.append(
            make_check(
                check_id="gstin_state_vs_address",
                gate=4,
                category="consistency",
                method="deterministic",
                result="skipped",
                severity="pass",
                evidence="blocked by missing document (see completeness)",
            )
        )
    elif cert_gstin and form_gstin != cert_gstin:
        checks.append(
            make_check(
                check_id="gstin_state_vs_address",
                gate=4,
                category="consistency",
                method="deterministic",
                result="skipped",
                severity="pass",
                evidence="Skipped because form and certificate GSTIN disagree",
            )
        )
    elif not cert_gstin:
        checks.append(
            make_check(
                check_id="gstin_state_vs_address",
                gate=4,
                category="consistency",
                method="deterministic",
                result="skipped",
                severity="pending_item",
                evidence="blocked by unreadable document",
                pending_item=_pending(
                    "tax_certificate",
                    "GSTIN state could not be checked without certificate GSTIN",
                    "Provide a readable tax certificate",
                ),
            )
        )
    elif not decoded_state:
        checks.append(
            make_check(
                check_id="gstin_state_vs_address",
                gate=4,
                category="consistency",
                method="deterministic",
                result="skipped",
                severity="pass",
                evidence="GSTIN state code could not be decoded",
            )
        )
    else:
        gstin_state = _canonical_state(decoded_state)
        address_state = _canonical_state(form.address.state)
        consistent = gstin_state == address_state
        checks.append(
            make_check(
                check_id="gstin_state_vs_address",
                gate=4,
                category="consistency",
                method="deterministic",
                result="pass" if consistent else "fail",
                severity="pass" if consistent else "hard_fail",
                evidence=f"GSTIN state {decoded_state} compared with address state {form.address.state}",
            )
        )

    return checks
