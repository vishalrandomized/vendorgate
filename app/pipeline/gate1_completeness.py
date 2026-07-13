"""Gate 1: deterministic completeness checks."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.pipeline.helpers import make_check
from app.profiles import FIELD_LABELS, PROFILES
from app.schemas import CheckResult, PendingItem, SubmissionForm


def _get_nested(obj: Any, path: str) -> Any:
    value = obj
    for part in path.split("."):
        value = getattr(value, part)
    return value


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _pending(item: str, label: str, detail: str) -> PendingItem:
    return PendingItem(
        item=item,
        detail=detail,
        action_required=f"Provide {label}",
    )


async def run(
    form: SubmissionForm, documents: dict[str, Path | None]
) -> list[CheckResult]:
    """Return one completeness check per required IN field/document."""
    checks: list[CheckResult] = []

    try:
        country = (form.country or "").strip().upper()
        if country in PROFILES:
            checks.append(
                make_check(
                    check_id="country_profile_known",
                    gate=1,
                    category="completeness",
                    method="deterministic",
                    result="pass",
                    severity="pass",
                    evidence=f"Country profile found for {country}",
                )
            )
        else:
            checks.append(
                make_check(
                    check_id="country_profile_known",
                    gate=1,
                    category="completeness",
                    method="deterministic",
                    result="fail",
                    severity="hard_fail",
                    evidence=f"No country profile found for {country or '(blank)'}",
                )
            )

        profile = PROFILES["IN"]
        for field in profile["required_form_fields"]:
            label = FIELD_LABELS.get(field, field.replace("_", " "))
            try:
                value = _get_nested(form, field)
                present = _is_present(value)
            except Exception as exc:  # pragma: no cover - defensive wrapper
                checks.append(
                    make_check(
                        check_id=f"field_present__{field.replace('.', '_')}",
                        gate=1,
                        category="completeness",
                        method="deterministic",
                        result="error",
                        severity="pending_item",
                        evidence=f"Could not inspect {field}: {exc}",
                        pending_item=_pending(field, label, f"Unable to inspect {label}"),
                    )
                )
                continue

            checks.append(
                make_check(
                    check_id=f"field_present__{field.replace('.', '_')}",
                    gate=1,
                    category="completeness",
                    method="deterministic",
                    result="pass" if present else "fail",
                    severity="pass" if present else "pending_item",
                    evidence=f"{label} is present" if present else f"{label} is missing",
                    pending_item=None
                    if present
                    else _pending(field, label, f"Required field missing: {label}"),
                )
            )

        for document in profile["required_documents"]:
            label = FIELD_LABELS.get(document, document.replace("_", " "))
            value = documents.get(document)
            present = value is not None and bool(str(value).strip())
            checks.append(
                make_check(
                    check_id=f"doc_present__{document}",
                    gate=1,
                    category="completeness",
                    method="deterministic",
                    result="pass" if present else "fail",
                    severity="pass" if present else "pending_item",
                    evidence=f"{label} is present" if present else f"{label} is missing",
                    pending_item=None
                    if present
                    else _pending(document, label, f"Required document missing: {label}"),
                )
            )
    except Exception as exc:  # pragma: no cover - final no-raise guard
        return [
            make_check(
                check_id="gate1_completeness_error",
                gate=1,
                category="completeness",
                method="deterministic",
                result="error",
                severity="pending_item",
                evidence=f"Completeness gate failed unexpectedly: {exc}",
                pending_item=PendingItem(
                    item="gate1_completeness",
                    detail="Unable to complete deterministic completeness checks",
                    action_required="Review submission completeness",
                    internal_only=True,
                ),
            )
        ]

    return checks
