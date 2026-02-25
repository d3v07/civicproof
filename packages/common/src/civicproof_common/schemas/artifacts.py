from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DataSource(StrEnum):
    USASPENDING = "usaspending"
    SAM_GOV = "sam_gov"
    SEC_EDGAR = "sec_edgar"
    DOJ = "doj"
    OVERSIGHT_GOV = "oversight_gov"
    OPENFEC = "openfec"
    MANUAL = "manual"


class DocType(StrEnum):
    CONTRACT_AWARD = "contract_award"
    PRESS_RELEASE = "press_release"
    SEC_FILING = "sec_filing"
    IG_REPORT = "ig_report"
    SAM_REGISTRATION = "sam_registration"
    FEC_FILING = "fec_filing"
    UNKNOWN = "unknown"


class RawArtifact(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    artifact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: DataSource
    source_url: str
    content_hash: str
    storage_path: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
    ingest_run_id: str | None = None


class ParsedDoc(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    doc_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    artifact_id: str
    doc_type: DocType
    extracted_text: str
    structured_data: dict[str, Any] = Field(default_factory=dict)
    parsed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
