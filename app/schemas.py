from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["pass", "soft_flag", "pending_item", "hard_fail"]
CheckResultStatus = Literal["pass", "warn", "fail", "error", "skipped"]
Method = Literal["deterministic", "llm", "external_api", "simulated_api"]
Outcome = Literal["approved", "pending", "rejected"]
Category = Literal[
    "completeness", "extraction", "format", "consistency", "credibility"
]


class Address(BaseModel):
    line1: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""


class Bank(BaseModel):
    account_number: str = ""
    ifsc: str = ""
    beneficiary_name: str = ""


class Contact(BaseModel):
    email: str = ""
    phone: str = ""


class SubmissionForm(BaseModel):
    country: str = "IN"
    legal_name: str = ""
    trade_name: str | None = None
    address: Address = Field(default_factory=Address)
    tax_id: str = ""
    bank: Bank = Field(default_factory=Bank)
    contact: Contact = Field(default_factory=Contact)


class PendingItem(BaseModel):
    item: str
    detail: str
    action_required: str
    internal_only: bool = False


class CheckResult(BaseModel):
    check_id: str
    gate: int
    category: Category
    method: Method
    result: CheckResultStatus
    severity: Severity
    evidence: str
    llm_rationale: str | None = None
    duration_ms: int = 0
    pending_item: PendingItem | None = None


class Decision(BaseModel):
    outcome: Outcome
    hard_fails: list[str]
    soft_flags: list[str]
    pending_items: list[PendingItem]
    summary: str


class RunResult(BaseModel):
    submission_id: str
    country_profile: str
    vendor_legal_name: str
    status: Outcome
    checks: list[CheckResult]
    decision: Decision
    vendor_email_draft: str | None = None
    audit: dict[str, Any]
    extracted: dict[str, Any] = Field(default_factory=dict)


class SubmissionListItem(BaseModel):
    id: str
    vendor_legal_name: str
    country: str
    status: str
    hard_fail_count: int = 0
    pending_count: int = 0
    flag_count: int = 0
    received_at: datetime
    decided_at: datetime | None = None


class FixtureInfo(BaseModel):
    name: str
    title: str
    expected_outcome: Outcome
    description: str


class DemoKitInfo(BaseModel):
    id: str
    fixture: str
    title: str
    expected_outcome: Outcome
    description: str
    has_bank_proof: bool
    path: str
