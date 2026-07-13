from itertools import product

from app.pipeline.decision import decide
from app.schemas import CheckResult, PendingItem


def _check(check_id: str, severity: str) -> CheckResult:
    pending_item = None
    if severity == "pending_item":
        pending_item = PendingItem(
            item=check_id,
            detail=f"{check_id} needs correction",
            action_required=f"Resolve {check_id}",
        )

    return CheckResult(
        check_id=check_id,
        gate=1,
        category="completeness",
        method="deterministic",
        result="pass" if severity in {"pass", "soft_flag"} else "fail",
        severity=severity,
        evidence=f"{check_id} evidence",
        pending_item=pending_item,
    )


def test_decision_engine_all_hard_pending_flag_combinations():
    for has_hard, has_pending, has_flags in product([False, True], repeat=3):
        checks = [_check("baseline", "pass")]
        if has_hard:
            checks.append(_check("hard_check", "hard_fail"))
        if has_pending:
            checks.append(_check("pending_check", "pending_item"))
        if has_flags:
            checks.append(_check("flag_check", "soft_flag"))

        decision = decide(checks)

        expected = "rejected" if has_hard else "pending" if has_pending else "approved"
        assert decision.outcome == expected
        assert decision.hard_fails == (["hard_check"] if has_hard else [])
        assert decision.soft_flags == (["flag_check"] if has_flags else [])
        assert len(decision.pending_items) == (1 if has_pending else 0)
