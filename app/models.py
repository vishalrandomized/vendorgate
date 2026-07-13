from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Submission(SQLModel, table=True):
    id: str = Field(primary_key=True)
    form_json: str
    country: str
    vendor_legal_name: str
    tax_certificate_path: str | None = None
    bank_proof_path: str | None = None
    received_at: datetime = Field(default_factory=utcnow)


class Run(SQLModel, table=True):
    id: str = Field(primary_key=True)
    submission_id: str = Field(foreign_key="submission.id", index=True)
    status: str = "running"
    result_json: str | None = None
    events_json: str = "[]"
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class SanctionsCache(SQLModel, table=True):
    normalized_name: str = Field(primary_key=True)
    response_json: str
    fetched_at: datetime = Field(default_factory=utcnow)
