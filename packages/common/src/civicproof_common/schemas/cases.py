from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CaseStatus(StrEnum):
    PENDING = "pending"
    INGESTING = "ingesting"
    ANALYZING = "analyzing"
    COMPOSING = "composing"
    AUDITING = "auditing"
    COMPLETE = "complete"
    FAILED = "failed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ClaimType(StrEnum):
    RISK_SIGNAL = "risk_signal"
    HYPOTHESIS = "hypothesis"
    FINDING = "finding"
    CANNOT_CONCLUDE = "cannot_conclude"


class Case(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    case_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    status: CaseStatus = CaseStatus.PENDING
    seed_input: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Claim(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    claim_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    statement: str
    claim_type: ClaimType
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    is_audited: bool = False
    audit_passed: bool | None = None


class Citation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    citation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim_id: str
    artifact_id: str
    excerpt: str
    page_ref: str | None = None


class AuditEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    audit_event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str
    stage: str
    policy_decision: str
    detail: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CasePack(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    case_id: str
    claims: list[Claim]
    citations: list[Citation]
    audit_events: list[AuditEvent]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    pack_hash: str | None = None
