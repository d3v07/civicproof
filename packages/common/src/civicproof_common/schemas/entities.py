from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EntityType(StrEnum):
    VENDOR = "vendor"
    INDIVIDUAL = "individual"
    ORGANIZATION = "organization"
    GOVERNMENT_AGENCY = "government_agency"
    UNKNOWN = "unknown"


class RelationshipType(StrEnum):
    OWNS = "owns"
    EMPLOYS = "employs"
    CONTRACTS_WITH = "contracts_with"
    SUBSIDIARY_OF = "subsidiary_of"
    AFFILIATED_WITH = "affiliated_with"
    AWARDED_BY = "awarded_by"


class Entity(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_type: EntityType
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    uei: str | None = None
    cage_code: str | None = None
    duns: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Relationship(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    relationship_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_entity_id: str
    target_entity_id: str
    rel_type: RelationshipType
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class EntityMention(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mention_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    raw_text: str
    source_artifact_id: str
    offset_start: int = Field(ge=0)
    offset_end: int = Field(ge=0)
    resolved_entity_id: str | None = None
