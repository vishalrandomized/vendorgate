"""Pure decision engine — severity → outcome. No LLM."""
from __future__ import annotations

from app.schemas import CheckResult, Decision, PendingItem


def decide(checks: list[CheckResult]) -> Decision:
    hard = [c for c in checks if c.severity == "hard_fail"]
    pend = [c for c in checks if c.severity == "pending_item"]
    flags = [c for c in checks if c.severity == "soft_flag"]

    if hard:
        outcome = "rejected"
    elif pend:
        outcome = "pending"
    else:
        outcome = "approved"

    pending_items: list[PendingItem] = []
    for c in pend:
        if c.pending_item is not None:
            pending_items.append(c.pending_item)
        else:
            pending_items.append(
                PendingItem(
                    item=c.check_id,
                    detail=c.evidence,
                    action_required=f"Resolve issue: {c.check_id}",
                )
            )

    hard_ids = [c.check_id for c in hard]
    flag_ids = [c.check_id for c in flags]

    if outcome == "approved":
        summary = (
            f"All {len(checks)} checks passed. "
            f"{len(flags)} advisory flag(s) recorded."
        )
    elif outcome == "pending":
        summary = (
            f"{len(pend)} item(s) require vendor action before approval."
        )
    else:
        ids = ", ".join(hard_ids) if hard_ids else "(none)"
        summary = (
            f"Hard failure on {ids}: recommend manual review. "
            "Not routed to vendor for correction."
        )

    return Decision(
        outcome=outcome,
        hard_fails=hard_ids,
        soft_flags=flag_ids,
        pending_items=pending_items,
        summary=summary,
    )
