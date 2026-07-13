"""Gate 3: deterministic form format checks."""
from __future__ import annotations

import re

from app.pipeline.helpers import make_check
from app.schemas import CheckResult, PendingItem, SubmissionForm
from app.validation.gstin import validate_gstin_parts
from app.validation.ifsc import is_valid_ifsc

POSTAL_CODE_RE = re.compile(r"^\d{6}$")


def _pending(item: str, detail: str, action_required: str) -> PendingItem:
    return PendingItem(item=item, detail=detail, action_required=action_required)


def _blocked(check_id: str, evidence: str) -> CheckResult:
    return make_check(
        check_id=check_id,
        gate=3,
        category="format",
        method="deterministic",
        result="skipped",
        severity="pass",
        evidence=evidence,
    )


async def run(form: SubmissionForm) -> list[CheckResult]:
    checks: list[CheckResult] = []
    gstin = (form.tax_id or "").strip().upper()
    parts = validate_gstin_parts(gstin)
    loose_structure_ok = bool(parts["loose_structure_ok"])

    checks.append(
        make_check(
            check_id="gstin_structure",
            gate=3,
            category="format",
            method="deterministic",
            result="pass" if loose_structure_ok else "fail",
            severity="pass" if loose_structure_ok else "pending_item",
            evidence="GSTIN has valid 15-character structure"
            if loose_structure_ok
            else "GSTIN does not match the expected 15-character structure",
            pending_item=None
            if loose_structure_ok
            else _pending(
                "tax_id",
                "GSTIN structure is invalid",
                "Provide a valid 15-character GSTIN",
            ),
        )
    )

    if not loose_structure_ok:
        checks.append(_blocked("gstin_taxpayer_type", "Blocked by invalid GSTIN structure"))

        if len(gstin) == 15:
            state_ok = bool(parts["state_ok"])
            checks.append(
                make_check(
                    check_id="gstin_state_code",
                    gate=3,
                    category="format",
                    method="deterministic",
                    result="pass" if state_ok else "fail",
                    severity="pass" if state_ok else "hard_fail",
                    evidence=f"GSTIN state code maps to {parts['state_name']}"
                    if state_ok
                    else "GSTIN state code is unknown",
                )
            )

            pan_ok = bool(parts["pan_ok"])
            checks.append(
                make_check(
                    check_id="gstin_embedded_pan",
                    gate=3,
                    category="format",
                    method="deterministic",
                    result="pass" if pan_ok else "fail",
                    severity="pass" if pan_ok else "hard_fail",
                    evidence="GSTIN contains a valid embedded PAN"
                    if pan_ok
                    else "GSTIN embedded PAN is invalid",
                )
            )

            checksum_ok = bool(parts["checksum_ok"])
            checks.append(
                make_check(
                    check_id="gstin_checksum",
                    gate=3,
                    category="format",
                    method="deterministic",
                    result="pass" if checksum_ok else "fail",
                    severity="pass" if checksum_ok else "pending_item",
                    evidence="GSTIN checksum matches"
                    if checksum_ok
                    else (
                        "GSTIN checksum mismatch"
                        if parts["expected_checksum"] is None
                        else f"GSTIN checksum mismatch; expected {parts['expected_checksum']}"
                    ),
                    pending_item=None
                    if checksum_ok
                    else _pending(
                        "tax_id",
                        "GSTIN checksum does not match the supplied value",
                        "Provide the correct GSTIN",
                    ),
                )
            )
        else:
            checks.extend(
                [
                    _blocked("gstin_state_code", "Blocked by invalid GSTIN length"),
                    _blocked("gstin_embedded_pan", "Blocked by invalid GSTIN length"),
                    _blocked("gstin_checksum", "Blocked by invalid GSTIN length"),
                ]
            )
    else:
        nonstandard = bool(parts["nonstandard_taxpayer_type"])
        checks.append(
            make_check(
                check_id="gstin_taxpayer_type",
                gate=3,
                category="format",
                method="deterministic",
                result="warn" if nonstandard else "pass",
                severity="soft_flag" if nonstandard else "pass",
                evidence="GSTIN taxpayer type is nonstandard"
                if nonstandard
                else "GSTIN taxpayer type is standard",
            )
        )

        state_ok = bool(parts["state_ok"])
        checks.append(
            make_check(
                check_id="gstin_state_code",
                gate=3,
                category="format",
                method="deterministic",
                result="pass" if state_ok else "fail",
                severity="pass" if state_ok else "hard_fail",
                evidence=f"GSTIN state code maps to {parts['state_name']}"
                if state_ok
                else "GSTIN state code is unknown",
            )
        )

        pan_ok = bool(parts["pan_ok"])
        checks.append(
            make_check(
                check_id="gstin_embedded_pan",
                gate=3,
                category="format",
                method="deterministic",
                result="pass" if pan_ok else "fail",
                severity="pass" if pan_ok else "hard_fail",
                evidence="GSTIN contains a valid embedded PAN"
                if pan_ok
                else "GSTIN embedded PAN is invalid",
            )
        )

        checksum_ok = bool(parts["checksum_ok"])
        checks.append(
            make_check(
                check_id="gstin_checksum",
                gate=3,
                category="format",
                method="deterministic",
                result="pass" if checksum_ok else "fail",
                severity="pass" if checksum_ok else "pending_item",
                evidence="GSTIN checksum matches"
                if checksum_ok
                else (
                    "GSTIN checksum mismatch"
                    if parts["expected_checksum"] is None
                    else f"GSTIN checksum mismatch; expected {parts['expected_checksum']}"
                ),
                pending_item=None
                if checksum_ok
                else _pending(
                    "tax_id",
                    "GSTIN checksum does not match the supplied value",
                    "Provide the correct GSTIN",
                ),
            )
        )

    ifsc_ok = is_valid_ifsc(form.bank.ifsc)
    checks.append(
        make_check(
            check_id="ifsc_format",
            gate=3,
            category="format",
            method="deterministic",
            result="pass" if ifsc_ok else "fail",
            severity="pass" if ifsc_ok else "pending_item",
            evidence="IFSC format is valid" if ifsc_ok else "IFSC format is invalid",
            pending_item=None
            if ifsc_ok
            else _pending("bank.ifsc", "IFSC format is invalid", "Provide a valid IFSC"),
        )
    )

    postal_ok = bool(POSTAL_CODE_RE.match((form.address.postal_code or "").strip()))
    checks.append(
        make_check(
            check_id="postal_code_format",
            gate=3,
            category="format",
            method="deterministic",
            result="pass" if postal_ok else "fail",
            severity="pass" if postal_ok else "pending_item",
            evidence="Postal code is a 6-digit code"
            if postal_ok
            else "Postal code must be exactly 6 digits",
            pending_item=None
            if postal_ok
            else _pending(
                "address.postal_code",
                "Postal code format is invalid",
                "Provide a valid 6-digit postal code",
            ),
        )
    )

    return checks
