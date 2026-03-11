"""initial schema — all 15 tables

Revision ID: 0001
Revises:
Create Date: 2026-02-24 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_source",
        sa.Column("source_id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("rate_limit_rps", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("requires_api_key", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "ingest_run",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("data_source.source_id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("artifacts_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_ingest_run_source_status", "ingest_run", ["source_id", "status"])

    op.create_table(
        "raw_artifact",
        sa.Column("artifact_id", sa.String(36), primary_key=True),
        sa.Column(
            "ingest_run_id",
            sa.String(36),
            sa.ForeignKey("ingest_run.run_id"),
            nullable=True,
        ),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("source", "content_hash", name="uq_artifact_source_hash"),
    )
    op.create_index("ix_artifact_source_hash", "raw_artifact", ["source", "content_hash"])
    op.create_index("ix_artifact_retrieved_at", "raw_artifact", ["retrieved_at"])

    op.create_table(
        "parsed_doc",
        sa.Column("doc_id", sa.String(36), primary_key=True),
        sa.Column(
            "artifact_id",
            sa.String(36),
            sa.ForeignKey("raw_artifact.artifact_id"),
            nullable=False,
        ),
        sa.Column("doc_type", sa.String(64), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("structured_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "parsed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_parsed_doc_artifact", "parsed_doc", ["artifact_id"])

    op.create_table(
        "entity",
        sa.Column("entity_id", sa.String(36), primary_key=True),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("uei", sa.String(12), nullable=True),
        sa.Column("cage_code", sa.String(5), nullable=True),
        sa.Column("duns", sa.String(9), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_entity_type_name", "entity", ["entity_type", "canonical_name"])
    op.create_index("ix_entity_uei", "entity", ["uei"])
    op.create_index("ix_entity_cage_code", "entity", ["cage_code"])

    op.create_table(
        "relationship",
        sa.Column("relationship_id", sa.String(36), primary_key=True),
        sa.Column(
            "source_entity_id",
            sa.String(36),
            sa.ForeignKey("entity.entity_id"),
            nullable=False,
        ),
        sa.Column(
            "target_entity_id",
            sa.String(36),
            sa.ForeignKey("entity.entity_id"),
            nullable=False,
        ),
        sa.Column("rel_type", sa.String(64), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("provenance_artifact_id", sa.String(36), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_relationship_source", "relationship", ["source_entity_id"])
    op.create_index("ix_relationship_target", "relationship", ["target_entity_id"])
    op.create_index("ix_relationship_type", "relationship", ["rel_type"])

    op.create_table(
        "entity_mention",
        sa.Column("mention_id", sa.String(36), primary_key=True),
        sa.Column(
            "source_artifact_id",
            sa.String(36),
            sa.ForeignKey("raw_artifact.artifact_id"),
            nullable=False,
        ),
        sa.Column(
            "resolved_entity_id",
            sa.String(36),
            sa.ForeignKey("entity.entity_id"),
            nullable=True,
        ),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("offset_start", sa.Integer(), nullable=False),
        sa.Column("offset_end", sa.Integer(), nullable=False),
    )
    op.create_index("ix_entity_mention_artifact", "entity_mention", ["source_artifact_id"])

    op.create_table(
        "case",
        sa.Column("case_id", sa.String(36), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("seed_input", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_case_status", "case", ["status"])

    op.create_table(
        "claim",
        sa.Column("claim_id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("case.case_id"), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_audited", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("audit_passed", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_claim_case_status", "claim", ["case_id", "is_audited"])

    op.create_table(
        "citation",
        sa.Column("citation_id", sa.String(36), primary_key=True),
        sa.Column("claim_id", sa.String(36), sa.ForeignKey("claim.claim_id"), nullable=False),
        sa.Column(
            "artifact_id",
            sa.String(36),
            sa.ForeignKey("raw_artifact.artifact_id"),
            nullable=False,
        ),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("page_ref", sa.String(64), nullable=True),
    )
    op.create_index("ix_citation_claim", "citation", ["claim_id"])

    op.create_table(
        "audit_event",
        sa.Column("audit_event_id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("case.case_id"), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("policy_decision", sa.String(64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_audit_event_case", "audit_event", ["case_id"])

    op.create_table(
        "policy_decision",
        sa.Column("decision_id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("case.case_id"), nullable=False),
        sa.Column("policy_name", sa.String(128), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_policy_decision_case", "policy_decision", ["case_id"])

    op.create_table(
        "eval_run",
        sa.Column("eval_run_id", sa.String(36), primary_key=True),
        sa.Column("eval_suite", sa.String(128), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("parameters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("summary", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_eval_run_suite_status", "eval_run", ["eval_suite", "status"])

    op.create_table(
        "eval_result",
        sa.Column("result_id", sa.String(36), primary_key=True),
        sa.Column(
            "eval_run_id",
            sa.String(36),
            sa.ForeignKey("eval_run.eval_run_id"),
            nullable=False,
        ),
        sa.Column("case_id", sa.String(36), nullable=True),
        sa.Column("evaluator", sa.String(128), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_eval_result_run", "eval_result", ["eval_run_id"])

    op.create_table(
        "case_pack",
        sa.Column("pack_id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("case.case_id"), nullable=False),
        sa.Column("pack_hash", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("claim_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("citation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("all_claims_audited", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_case_pack_case", "case_pack", ["case_id"])
    op.create_index("ix_case_pack_hash", "case_pack", ["pack_hash"])


def downgrade() -> None:
    op.drop_table("case_pack")
    op.drop_table("eval_result")
    op.drop_table("eval_run")
    op.drop_table("policy_decision")
    op.drop_table("audit_event")
    op.drop_table("citation")
    op.drop_table("claim")
    op.drop_table("case")
    op.drop_table("entity_mention")
    op.drop_table("relationship")
    op.drop_table("entity")
    op.drop_table("parsed_doc")
    op.drop_table("raw_artifact")
    op.drop_table("ingest_run")
    op.drop_table("data_source")
