"""Shared helpers for emitting CheckResult objects from gates."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from app.schemas import CheckResult, Method, PendingItem, Severity, CheckResultStatus, Category


@contextmanager
def timed() -> Iterator[list[int]]:
    box: list[int] = [0]
    start = time.perf_counter()
    try:
        yield box
    finally:
        box[0] = int((time.perf_counter() - start) * 1000)


def make_check(
    *,
    check_id: str,
    gate: int,
    category: Category,
    method: Method,
    result: CheckResultStatus,
    severity: Severity,
    evidence: str,
    duration_ms: int = 0,
    llm_rationale: str | None = None,
    pending_item: PendingItem | None = None,
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        gate=gate,
        category=category,
        method=method,
        result=result,
        severity=severity,
        evidence=evidence,
        duration_ms=duration_ms,
        llm_rationale=llm_rationale,
        pending_item=pending_item,
    )
