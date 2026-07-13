"""Gate 5: credibility checks backed by external and mock services."""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from sqlmodel import Session

from app.pipeline.helpers import make_check, timed
from app.schemas import CheckResult, Method, PendingItem
from app.services.llm import strict_json as default_strict_json
from app.services.pennydrop import verify as verify_bank_account
from app.services.registry import MockGstRegistry
from app.services.sanctions import screen_company
from app.validation.names import BAND_LOW, PASS_THRESHOLD, normalize, similarity

StrictJson = Callable[[str, str, str, int], Awaitable[dict | None]]

FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "hotmail.com",
    "rediffmail.com",
    "proton.me",
}


def _pending(item: str, detail: str, action_required: str, *, internal_only: bool = False) -> PendingItem:
    return PendingItem(
        item=item,
        detail=detail,
        action_required=action_required,
        internal_only=internal_only,
    )


def _evidence_name(label: str, left: str, right: str, score: float) -> str:
    return f"{label}: '{left}' vs '{right}' scored {score:.2f}"


async def _adjudicate_name_match(
    *,
    check_id: str,
    method: Method,
    label: str,
    expected_name: str,
    observed_name: str,
    score: float | None,
    strict_json_func: StrictJson,
    missing_detail: str,
) -> list[CheckResult]:
    if score is None:
        detail = f"{missing_detail}; could not score name match"
        return [
            make_check(
                check_id=check_id,
                gate=5,
                category="credibility",
                method=method,
                result="error",
                severity="pending_item",
                evidence=detail,
                pending_item=_pending(
                    check_id,
                    detail,
                    "Review the vendor name against the verified external record",
                ),
            )
        ]

    evidence = _evidence_name(label, expected_name, observed_name, score)
    if score >= PASS_THRESHOLD:
        return [
            make_check(
                check_id=check_id,
                gate=5,
                category="credibility",
                method=method,
                result="pass",
                severity="pass",
                evidence=evidence,
            )
        ]
    if score < BAND_LOW:
        return [
            make_check(
                check_id=check_id,
                gate=5,
                category="credibility",
                method=method,
                result="fail",
                severity="hard_fail",
                evidence=evidence,
            )
        ]

    try:
        llm_payload = await strict_json_func(
            (
                "You adjudicate whether two vendor names refer to the same legal entity. "
                "If the distinctive business words differ (e.g. Enterprises vs Logistics, "
                "Exports, or Trading), return different_entity or uncertain — do not treat "
                "a shared first token alone as same_entity. "
                "Return strict JSON only."
            ),
            (
                f"Compare these names:\n"
                f"Form name: {expected_name}\n"
                f"Verified name: {observed_name}\n"
                f"Similarity score: {score:.2f}"
            ),
            json.dumps(
                {
                    "verdict": "same_entity | different_entity | uncertain",
                    "rationale": "short explanation",
                }
            ),
            1,
        )
        verdict = str((llm_payload or {}).get("verdict", "uncertain")).strip()
        rationale = str((llm_payload or {}).get("rationale", "")).strip()
    except Exception as exc:  # noqa: BLE001 - gates must contain injected LLM failures.
        verdict = "uncertain"
        rationale = f"LLM adjudication failed: {exc}"

    if verdict == "same_entity":
        return [
            make_check(
                check_id=check_id,
                gate=5,
                category="credibility",
                method="llm",
                result="pass",
                severity="pass",
                evidence=evidence,
                llm_rationale=rationale,
            ),
            make_check(
                check_id="name_match_llm_assisted",
                gate=5,
                category="credibility",
                method="llm",
                result="warn",
                severity="soft_flag",
                evidence=f"LLM assisted medium-band name match for {check_id}",
                llm_rationale=rationale,
            ),
        ]

    detail = f"{evidence}; LLM verdict: {verdict}"
    return [
        make_check(
            check_id=check_id,
            gate=5,
            category="credibility",
            method="llm",
            result="warn",
            severity="pending_item",
            evidence=detail,
            llm_rationale=rationale or None,
            pending_item=_pending(
                check_id,
                "Vendor name could not be confidently matched",
                "Review the vendor name against the verified external record",
            ),
        )
    ]


async def _sanctions_check(form: Any, session: Session, audit: dict[str, Any]) -> CheckResult:
    legal_name = getattr(form, "legal_name", "")
    with timed() as duration:
        result = await screen_company(legal_name, session)

    audit["sanctions_source"] = result.get("source")
    audit["sanctions_top_score"] = result.get("top_score")
    audit["sanctions_top_caption"] = result.get("top_caption")
    audit["sanctions_datasets"] = result.get("datasets", [])
    if result.get("error"):
        audit["sanctions_error"] = result.get("error")

    if result.get("source") == "unavailable":
        detail = f"Sanctions screening unavailable: {result.get('error') or 'unknown error'}"
        return make_check(
            check_id="sanctions_screening",
            gate=5,
            category="credibility",
            method="external_api",
            result="error",
            severity="pending_item",
            evidence=detail,
            duration_ms=duration[0],
            pending_item=_pending(
                "sanctions_screening",
                detail,
                "Retry sanctions screening or complete manual screening review",
                internal_only=True,
            ),
        )

    score = float(result.get("top_score") or 0.0)
    caption = result.get("top_caption") or "no match"
    datasets = ", ".join(result.get("datasets") or [])
    evidence = (
        f"OpenSanctions {result.get('source')} score {score:.2f}; "
        f"top match: {caption}; datasets: {datasets or 'none'}"
    )

    if score >= 0.85:
        return make_check(
            check_id="sanctions_screening",
            gate=5,
            category="credibility",
            method="external_api",
            result="fail",
            severity="hard_fail",
            evidence=evidence,
            duration_ms=duration[0],
        )
    if score >= 0.50:
        return make_check(
            check_id="sanctions_screening",
            gate=5,
            category="credibility",
            method="external_api",
            result="warn",
            severity="pending_item",
            evidence=evidence,
            duration_ms=duration[0],
            pending_item=_pending(
                "sanctions_screening",
                evidence,
                "Manual screening review required — do not communicate a potential sanctions match to the vendor",
                internal_only=True,
            ),
        )
    return make_check(
        check_id="sanctions_screening",
        gate=5,
        category="credibility",
        method="external_api",
        result="pass",
        severity="pass",
        evidence=evidence,
        duration_ms=duration[0],
    )


def _pennydrop_error_check(check_id: str, error: str) -> CheckResult:
    detail = f"Mock bank directory lookup unavailable: {error}"
    return make_check(
        check_id=check_id,
        gate=5,
        category="credibility",
        method="simulated_api",
        result="error",
        severity="pending_item",
        evidence=detail,
        pending_item=_pending(
            check_id,
            detail,
            "Retry penny-drop verification or review bank proof manually",
        ),
    )


async def _pennydrop_checks(
    form: Any,
    audit: dict[str, Any],
    strict_json_func: StrictJson,
) -> list[CheckResult]:
    bank = getattr(form, "bank", None)
    account_number = getattr(bank, "account_number", "")
    ifsc = getattr(bank, "ifsc", "")
    beneficiary_name = getattr(bank, "beneficiary_name", "")

    with timed() as duration:
        verification = await verify_bank_account(account_number, ifsc)

    audit["pennydrop_source"] = "mock"
    audit["pennydrop_registered_name"] = verification.get("registered_name")

    checks: list[CheckResult] = []
    exists = verification.get("account_exists")
    if exists is True:
        checks.append(
            make_check(
                check_id="bank_account_exists",
                gate=5,
                category="credibility",
                method="simulated_api",
                result="pass",
                severity="pass",
                evidence="Mock bank directory confirms the bank account exists",
                duration_ms=duration[0],
            )
        )
    elif exists is False:
        detail = (
            "Account could not be verified against the mock bank directory; confirm account number and IFSC"
        )
        checks.append(
            make_check(
                check_id="bank_account_exists",
                gate=5,
                category="credibility",
                method="simulated_api",
                result="fail",
                severity="pending_item",
                evidence=detail,
                duration_ms=duration[0],
                pending_item=_pending(
                    "bank_account_exists",
                    detail,
                    "Confirm bank account number and IFSC with the vendor",
                ),
            )
        )
    else:
        detail = "Mock bank directory did not return account existence"
        checks.append(
            make_check(
                check_id="bank_account_exists",
                gate=5,
                category="credibility",
                method="simulated_api",
                result="error",
                severity="pending_item",
                evidence=detail,
                duration_ms=duration[0],
                pending_item=_pending(
                    "bank_account_exists",
                    detail,
                    "Review bank account existence manually",
                ),
            )
        )

    active = verification.get("active")
    if active is True:
        checks.append(
            make_check(
                check_id="bank_account_active",
                gate=5,
                category="credibility",
                method="simulated_api",
                result="pass",
                severity="pass",
                evidence="Mock bank directory confirms the bank account is active",
                duration_ms=duration[0],
            )
        )
    elif active is False:
        detail = "Mock bank directory reports the bank account is inactive; confirm details with the vendor"
        checks.append(
            make_check(
                check_id="bank_account_active",
                gate=5,
                category="credibility",
                method="simulated_api",
                result="fail",
                severity="pending_item",
                evidence=detail,
                duration_ms=duration[0],
                pending_item=_pending(
                    "bank_account_active",
                    detail,
                    "Confirm the bank account is active, or provide an alternate account",
                ),
            )
        )
    else:
        detail = "Mock bank directory did not return account active status"
        checks.append(
            make_check(
                check_id="bank_account_active",
                gate=5,
                category="credibility",
                method="simulated_api",
                result="error",
                severity="pending_item",
                evidence=detail,
                duration_ms=duration[0],
                pending_item=_pending(
                    "bank_account_active",
                    detail,
                    "Review bank account active status manually",
                ),
            )
        )

    registered_name = verification.get("registered_name") or ""
    score = similarity(beneficiary_name, registered_name) if registered_name else None
    checks.extend(
        await _adjudicate_name_match(
            check_id="name_match__pennydrop",
            method="simulated_api",
            label="Penny-drop name match",
            expected_name=beneficiary_name,
            observed_name=registered_name,
            score=score,
            strict_json_func=strict_json_func,
            missing_detail="Mock bank directory did not return a registered account name",
        )
    )

    return checks


async def _registry_checks(
    form: Any,
    audit: dict[str, Any],
    strict_json_func: StrictJson,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    registry = MockGstRegistry()
    gstin = getattr(form, "tax_id", "")
    legal_name = getattr(form, "legal_name", "")
    result = registry.lookup(gstin)

    audit["registry_found"] = result.get("found")
    audit["registry_status"] = result.get("status")
    audit["registry_legal_name"] = result.get("legal_name")

    if not result.get("found"):
        detail = f"GSTIN {gstin!r} was not found in the mock GST registry"
        checks.append(
            make_check(
                check_id="gst_registry_status",
                gate=5,
                category="credibility",
                method="simulated_api",
                result="warn",
                severity="pending_item",
                evidence=detail,
                pending_item=_pending(
                    "gst_registry_status",
                    detail,
                    "Confirm GST registration details with the vendor or registry evidence",
                ),
            )
        )
        return checks

    status = str(result.get("status") or "").strip()
    if status.lower() in {"cancelled", "canceled", "suspended"}:
        checks.append(
            make_check(
                check_id="gst_registry_status",
                gate=5,
                category="credibility",
                method="simulated_api",
                result="fail",
                severity="hard_fail",
                evidence=f"Mock GST registry status for {gstin!r} is {status!r}",
            )
        )
    elif status:
        checks.append(
            make_check(
                check_id="gst_registry_status",
                gate=5,
                category="credibility",
                method="simulated_api",
                result="pass",
                severity="pass",
                evidence=f"Mock GST registry status for {gstin!r} is {status!r}",
            )
        )
    else:
        detail = f"Mock GST registry did not return a status for {gstin!r}"
        checks.append(
            make_check(
                check_id="gst_registry_status",
                gate=5,
                category="credibility",
                method="simulated_api",
                result="error",
                severity="pending_item",
                evidence=detail,
                pending_item=_pending(
                    "gst_registry_status",
                    detail,
                    "Review GST registry status manually",
                ),
            )
        )

    registry_name = result.get("legal_name") or ""
    checks.extend(
        await _adjudicate_name_match(
            check_id="name_match__registry",
            method="simulated_api",
            label="GST registry name match",
            expected_name=legal_name,
            observed_name=registry_name,
            score=similarity(legal_name, registry_name) if registry_name else None,
            strict_json_func=strict_json_func,
            missing_detail="Mock GST registry did not return a legal name",
        )
    )
    return checks


def _email_checks(form: Any) -> list[CheckResult]:
    email = getattr(getattr(form, "contact", None), "email", "")
    domain = email.rsplit("@", 1)[-1].strip().lower() if "@" in email else ""
    if not domain:
        return [
            make_check(
                check_id="email_domain_free",
                gate=5,
                category="credibility",
                method="deterministic",
                result="skipped",
                severity="pass",
                evidence="No email domain available for credibility soft-signal checks",
            )
        ]

    checks: list[CheckResult] = []
    if domain in FREE_EMAIL_DOMAINS:
        checks.append(
            make_check(
                check_id="email_domain_free",
                gate=5,
                category="credibility",
                method="deterministic",
                result="warn",
                severity="soft_flag",
                evidence=f"Vendor contact email uses free domain {domain!r}",
            )
        )
        checks.append(
            make_check(
                check_id="email_domain_name_affinity",
                gate=5,
                category="credibility",
                method="deterministic",
                result="skipped",
                severity="pass",
                evidence="Domain-name affinity skipped for free email domain",
            )
        )
        return checks

    checks.append(
        make_check(
            check_id="email_domain_free",
            gate=5,
            category="credibility",
            method="deterministic",
            result="pass",
            severity="pass",
            evidence=f"Vendor contact email domain {domain!r} is not a common free provider",
        )
    )

    domain_root = domain.rsplit(".", 1)[0].replace(".", " ").replace("-", " ")
    legal_name = getattr(form, "legal_name", "")
    affinity = similarity(domain_root, normalize(legal_name))
    if affinity < 0.4:
        checks.append(
            make_check(
                check_id="email_domain_name_affinity",
                gate=5,
                category="credibility",
                method="deterministic",
                result="warn",
                severity="soft_flag",
                evidence=(
                    f"Email domain root {domain_root!r} has low affinity "
                    f"to legal name {legal_name!r}: {affinity:.2f}"
                ),
            )
        )
    else:
        checks.append(
            make_check(
                check_id="email_domain_name_affinity",
                gate=5,
                category="credibility",
                method="deterministic",
                result="pass",
                severity="pass",
                evidence=(
                    f"Email domain root {domain_root!r} has acceptable affinity "
                    f"to legal name {legal_name!r}: {affinity:.2f}"
                ),
            )
        )
    return checks


async def run(form, session, strict_json=None) -> tuple[list[CheckResult], dict]:
    strict_json_func: StrictJson = strict_json or default_strict_json
    checks: list[CheckResult] = []
    audit: dict[str, Any] = {}

    try:
        checks.append(await _sanctions_check(form, session, audit))
    except Exception as exc:  # noqa: BLE001 - external failures must become checks.
        detail = f"Sanctions screening failed unexpectedly: {exc}"
        audit["sanctions_source"] = "unavailable"
        audit["sanctions_error"] = str(exc)
        checks.append(
            make_check(
                check_id="sanctions_screening",
                gate=5,
                category="credibility",
                method="external_api",
                result="error",
                severity="pending_item",
                evidence=detail,
                pending_item=_pending(
                    "sanctions_screening",
                    detail,
                    "Retry sanctions screening or complete manual screening review",
                    internal_only=True,
                ),
            )
        )

    try:
        checks.extend(await _pennydrop_checks(form, audit, strict_json_func))
    except Exception as exc:  # noqa: BLE001 - keep Gate 5 contained.
        error = str(exc)
        audit["pennydrop_source"] = "unavailable"
        audit["pennydrop_error"] = error
        checks.extend(
            [
                _pennydrop_error_check("bank_account_exists", error),
                _pennydrop_error_check("bank_account_active", error),
                _pennydrop_error_check("name_match__pennydrop", error),
            ]
        )

    try:
        checks.extend(await _registry_checks(form, audit, strict_json_func))
    except Exception as exc:  # noqa: BLE001
        detail = f"Mock GST registry lookup failed unexpectedly: {exc}"
        audit["registry_error"] = str(exc)
        checks.append(
            make_check(
                check_id="gst_registry_status",
                gate=5,
                category="credibility",
                method="simulated_api",
                result="error",
                severity="pending_item",
                evidence=detail,
                pending_item=_pending(
                    "gst_registry_status",
                    detail,
                    "Review GST registration details manually",
                ),
            )
        )

    try:
        checks.extend(_email_checks(form))
    except Exception as exc:  # noqa: BLE001
        detail = f"Email credibility soft-signal checks failed unexpectedly: {exc}"
        audit["email_signal_error"] = str(exc)
        checks.append(
            make_check(
                check_id="email_domain_signals",
                gate=5,
                category="credibility",
                method="deterministic",
                result="error",
                severity="pending_item",
                evidence=detail,
                pending_item=_pending(
                    "email_domain_signals",
                    detail,
                    "Review vendor contact email manually",
                ),
            )
        )

    return checks, audit
