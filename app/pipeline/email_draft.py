"""Vendor-facing pending email drafting."""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from app.schemas import PendingItem
from app.services.llm import strict_json as default_strict_json

StrictJson = Callable[[str, str, str, int], Awaitable[dict | None]]

SIGN_OFF = "Vishal, AI Solutions Engineer, ZAMP"


def _field_snapshot(form: Any) -> dict[str, str]:
    bank = getattr(form, "bank", None)
    contact = getattr(form, "contact", None)
    return {
        "legal_name": getattr(form, "legal_name", ""),
        "tax_id": getattr(form, "tax_id", ""),
        "bank_account_number": getattr(bank, "account_number", ""),
        "ifsc": getattr(bank, "ifsc", ""),
        "beneficiary_name": getattr(bank, "beneficiary_name", ""),
        "contact_email": getattr(contact, "email", ""),
    }


def _apply_sign_off(email: str) -> str:
    """Force exactly one Best regards + SIGN_OFF block at the end."""
    text = email.rstrip()
    # Drop any existing closing (LLM often already includes one / blank lines).
    text = re.sub(
        r"(?:\r?\n)+\s*Best regards,?\s*(?:[\r\n].*)*\Z",
        "",
        text,
        flags=re.IGNORECASE,
    ).rstrip()
    return f"{text}\n\nBest regards,\n{SIGN_OFF}"


def _deterministic_template(form: Any, pending_items: list[PendingItem]) -> str:
    vendor_name = getattr(form, "legal_name", "") or "there"
    lines = [
        "Subject: Additional information required for vendor onboarding",
        "",
        f"Hello {vendor_name},",
        "",
        "Thank you for submitting your onboarding details. We need a little more information to complete the review:",
        "",
    ]
    for index, item in enumerate(pending_items, start=1):
        lines.append(
            f"{index}. {item.action_required}. Reference: \"{item.detail}\""
        )
    lines.extend(
        [
            "",
            "Please reply with the requested details or corrected documents, and we will continue the review promptly.",
            "",
            "Best regards,",
            SIGN_OFF,
        ]
    )
    return "\n".join(lines)


def _coerce_email(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    email = payload.get("email") or payload.get("body")
    subject = payload.get("subject")
    if not email:
        return None
    if subject and "subject:" not in str(email).lower()[:40]:
        return f"Subject: {subject}\n\n{email}"
    return str(email)


async def run(
    form: Any,
    outcome: str,
    pending_items: list[PendingItem],
    strict_json: StrictJson | None = None,
) -> str | None:
    """Draft one vendor email for pending submissions.

    Internal-only pending items are excluded. If only internal review remains,
    returns None so the UI can indicate that no vendor email should be sent.
    """
    if outcome != "pending":
        return None

    vendor_items = [item for item in pending_items if not item.internal_only]
    if not vendor_items:
        return None

    strict_json_func = strict_json or default_strict_json
    snapshot = _field_snapshot(form)
    items_text = "\n".join(
        (
            f"{index}. item={item.item!r}; detail={item.detail!r}; "
            f"action_required={item.action_required!r}"
        )
        for index, item in enumerate(vendor_items, start=1)
    )

    try:
        payload = await strict_json_func(
            "You draft concise vendor onboarding emails.",
            (
                "Write one professional, warm, specific email for a pending vendor onboarding case. "
                "Quote exact field values where relevant, number the requested items, and do not mention internal-only review. "
                f"End the email with exactly:\nBest regards,\n{SIGN_OFF}\n"
                "Do not invent any other signer name or title.\n\n"
                f"Form field snapshot: {snapshot!r}\n\n"
                f"Vendor-facing pending items:\n{items_text}"
            ),
            '{"subject":"email subject","body":"complete email body"}',
            1,
        )
        email = _coerce_email(payload)
        if email:
            return _apply_sign_off(email)
    except Exception:  # noqa: BLE001 - email drafting falls back deterministically.
        pass

    return _deterministic_template(form, vendor_items)
