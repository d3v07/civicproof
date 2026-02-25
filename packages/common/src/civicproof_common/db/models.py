from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class DataSourceModel(Base):
    __tablename__ = "data_source"

    source_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    rate_limit_rps: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    requires_api_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    ingest_runs: Mapped[list[IngestRunModel]] = relationship(
        "IngestRunModel", back_populates="data_source"
    )


class IngestRunModel(Base):
    __tablename__ = "ingest_run"

    run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("data_source.source_id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    artifacts_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    data_source: Mapped[DataSourceModel] = relationship(
        "DataSourceModel", back_populates="ingest_runs"
    )
    raw_artifacts: Mapped[list[RawArtifactModel]] = relationship(
        "RawArtifactModel", back_populates="ingest_run"
    )

    __table_args__ = (Index("ix_ingest_run_source_status", "source_id", "status"),)


class RawArtifactModel(Base):
    __tablename__ = "raw_artifact"

    artifact_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ingest_run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("ingest_run.run_id"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    ingest_run: Mapped[IngestRunModel | None] = relationship(
        "IngestRunModel", back_populates="raw_artifacts"
    )
    parsed_docs: Mapped[list[ParsedDocModel]] = relationship(
        "ParsedDocModel", back_populates="raw_artifact"
    )
    entity_mentions: Mapped[list[EntityMentionModel]] = relationship(
        "EntityMentionModel", back_populates="raw_artifact"
    )

    __table_args__ = (
        UniqueConstraint("source", "content_hash", name="uq_artifact_source_hash"),
        Index("ix_artifact_source_hash", "source", "content_hash"),
        Index("ix_artifact_retrieved_at", "retrieved_at"),
    )


class ParsedDocModel(Base):
    __tablename__ = "parsed_doc"

    doc_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    artifact_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("raw_artifact.artifact_id"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    structured_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    raw_artifact: Mapped[RawArtifactModel] = relationship(
        "RawArtifactModel", back_populates="parsed_docs"
    )

    __table_args__ = (Index("ix_parsed_doc_artifact", "artifact_id"),)


class EntityModel(Base):
    __tablename__ = "entity"

    entity_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    uei: Mapped[str | None] = mapped_column(String(12), nullable=True)
    cage_code: Mapped[str | None] = mapped_column(String(5), nullable=True)
    duns: Mapped[str | None] = mapped_column(String(9), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    mentions: Mapped[list[EntityMentionModel]] = relationship(
        "EntityMentionModel", back_populates="entity"
    )

    __table_args__ = (
        Index("ix_entity_type_name", "entity_type", "canonical_name"),
        Index("ix_entity_uei", "uei"),
        Index("ix_entity_cage_code", "cage_code"),
    )


class RelationshipModel(Base):
    __tablename__ = "relationship"

    relationship_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    source_entity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("entity.entity_id"), nullable=False
    )
    target_entity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("entity.entity_id"), nullable=False
    )
    rel_type: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    provenance_artifact_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), nullable=True
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        Index("ix_relationship_source", "source_entity_id"),
        Index("ix_relationship_target", "target_entity_id"),
        Index("ix_relationship_type", "rel_type"),
    )


class EntityMentionModel(Base):
    __tablename__ = "entity_mention"

    mention_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    source_artifact_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("raw_artifact.artifact_id"), nullable=False
    )
    resolved_entity_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("entity.entity_id"), nullable=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    offset_start: Mapped[int] = mapped_column(Integer, nullable=False)
    offset_end: Mapped[int] = mapped_column(Integer, nullable=False)

    raw_artifact: Mapped[RawArtifactModel] = relationship(
        "RawArtifactModel", back_populates="entity_mentions"
    )
    entity: Mapped[EntityModel | None] = relationship("EntityModel", back_populates="mentions")

    __table_args__ = (Index("ix_entity_mention_artifact", "source_artifact_id"),)


class CaseModel(Base):
    __tablename__ = "case"

    case_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    seed_input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    claims: Mapped[list[ClaimModel]] = relationship("ClaimModel", back_populates="case")
    audit_events: Mapped[list[AuditEventModel]] = relationship(
        "AuditEventModel", back_populates="case"
    )
    policy_decisions: Mapped[list[PolicyDecisionModel]] = relationship(
        "PolicyDecisionModel", back_populates="case"
    )
    case_packs: Mapped[list[CasePackModel]] = relationship("CasePackModel", back_populates="case")

    __table_args__ = (Index("ix_case_status", "status"),)


class ClaimModel(Base):
    __tablename__ = "claim"

    claim_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("case.case_id"), nullable=False
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_audited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    audit_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    case: Mapped[CaseModel] = relationship("CaseModel", back_populates="claims")
    citations: Mapped[list[CitationModel]] = relationship("CitationModel", back_populates="claim")

    __table_args__ = (Index("ix_claim_case_status", "case_id", "is_audited"),)


class CitationModel(Base):
    __tablename__ = "citation"

    citation_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    claim_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("claim.claim_id"), nullable=False
    )
    artifact_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("raw_artifact.artifact_id"), nullable=False
    )
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    page_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)

    claim: Mapped[ClaimModel] = relationship("ClaimModel", back_populates="citations")

    __table_args__ = (Index("ix_citation_claim", "claim_id"),)


class AuditEventModel(Base):
    __tablename__ = "audit_event"

    audit_event_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("case.case_id"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_decision: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    case: Mapped[CaseModel] = relationship("CaseModel", back_populates="audit_events")

    __table_args__ = (Index("ix_audit_event_case", "case_id"),)


class PolicyDecisionModel(Base):
    __tablename__ = "policy_decision"

    decision_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("case.case_id"), nullable=False
    )
    policy_name: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    case: Mapped[CaseModel] = relationship("CaseModel", back_populates="policy_decisions")

    __table_args__ = (Index("ix_policy_decision_case", "case_id"),)


class EvalRunModel(Base):
    __tablename__ = "eval_run"

    eval_run_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    eval_suite: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    results: Mapped[list[EvalResultModel]] = relationship(
        "EvalResultModel", back_populates="eval_run"
    )

    __table_args__ = (Index("ix_eval_run_suite_status", "eval_suite", "status"),)


class EvalResultModel(Base):
    __tablename__ = "eval_result"

    result_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    eval_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("eval_run.eval_run_id"), nullable=False
    )
    case_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    evaluator: Mapped[str] = mapped_column(String(128), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    eval_run: Mapped[EvalRunModel] = relationship("EvalRunModel", back_populates="results")

    __table_args__ = (Index("ix_eval_result_run", "eval_run_id"),)


class CasePackModel(Base):
    __tablename__ = "case_pack"

    pack_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("case.case_id"), nullable=False
    )
    pack_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    citation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    all_claims_audited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    case: Mapped[CaseModel] = relationship("CaseModel", back_populates="case_packs")

    __table_args__ = (
        Index("ix_case_pack_case", "case_id"),
        Index("ix_case_pack_hash", "pack_hash"),
    )
