from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventType(StrEnum):
    ARTIFACT_INGESTED = "artifact.ingested"
    ENTITY_RESOLVED = "entity.resolved"
    CASE_CREATED = "case.created"
    CASE_UPDATED = "case.updated"
    CLAIM_AUDITED = "claim.audited"
    ARTIFACT_PARSE_REQUESTED = "artifact.parse_requested"
    ENTITY_NORMALIZE_REQUESTED = "entity.normalize_requested"


class EventEnvelope(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    source: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any]
    idempotency_key: str

    @field_validator("idempotency_key")
    @classmethod
    def idempotency_key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("idempotency_key must not be empty")
        return v

    @classmethod
    def build(
        cls,
        event_type: EventType,
        source: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        key = idempotency_key or str(uuid.uuid4())
        return cls(
            event_type=event_type,
            source=source,
            payload=payload,
            idempotency_key=key,
        )
