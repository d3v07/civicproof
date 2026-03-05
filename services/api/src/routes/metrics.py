"""KPI Metrics Endpoint.

Returns aggregated system health and performance metrics.
Per sprint plan S8 and CLAUDE.md:
  - Public endpoint exposes NO PII or case-specific data
  - Aggregated counts and rates only
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from civicproof_common.db.models import (
    AuditEventModel,
    CaseModel,
    CasePackModel,
    DataSourceModel,
    EntityMentionModel,
    RawArtifactModel,
)
from civicproof_common.db.session import get_session
from civicproof_common.telemetry import StructuredLogger
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = StructuredLogger(__name__)
_stdlib_logger = logging.getLogger(__name__)


class Last24hMetrics(BaseModel):
    cases_created: int = 0
    artifacts_fetched: int = 0
    audit_blocks: int = 0
    model_cost_usd: float = 0.0


class PublicMetrics(BaseModel):
    audited_dossier_pass_rate: float = 0.0
    median_tip_to_dossier_seconds: float = 0.0
    hallucination_caught_rate: float = 0.0
    avg_cost_per_dossier_usd: float = 0.0
    entity_resolution_coverage: float = 0.0
    replay_determinism_rate: float = 1.0
    total_cases_processed: int = 0
    total_artifacts_ingested: int = 0
    sources_active: int = 0
    last_24h: Last24hMetrics = Last24hMetrics()


@router.get("/metrics/public", response_model=PublicMetrics)
async def get_public_metrics(
    db: AsyncSession = Depends(get_session),
) -> PublicMetrics:
    """Aggregated system health metrics — no PII, no case-specific data."""
    now = datetime.now(UTC)
    day_ago = now - timedelta(days=1)

    # Total cases
    total_cases_result = await db.execute(
        select(func.count()).select_from(CaseModel)
    )
    total_cases = total_cases_result.scalar() or 0

    # Total artifacts
    total_artifacts_result = await db.execute(
        select(func.count()).select_from(RawArtifactModel)
    )
    total_artifacts = total_artifacts_result.scalar() or 0

    # Active data sources
    sources_result = await db.execute(
        select(func.count()).select_from(DataSourceModel)
    )
    sources_active = sources_result.scalar() or 0

    # Case packs: pass rate
    total_packs_result = await db.execute(
        select(func.count()).select_from(CasePackModel)
    )
    total_packs = total_packs_result.scalar() or 0

    passed_packs_result = await db.execute(
        select(func.count())
        .select_from(CasePackModel)
        .where(CasePackModel.all_claims_audited.is_(True))
    )
    passed_packs = passed_packs_result.scalar() or 0
    pass_rate = passed_packs / total_packs if total_packs > 0 else 0.0

    # Last 24h: cases created
    cases_24h_result = await db.execute(
        select(func.count())
        .select_from(CaseModel)
        .where(CaseModel.created_at >= day_ago)
    )
    cases_24h = cases_24h_result.scalar() or 0

    # Last 24h: artifacts fetched
    artifacts_24h_result = await db.execute(
        select(func.count())
        .select_from(RawArtifactModel)
        .where(RawArtifactModel.retrieved_at >= day_ago)
    )
    artifacts_24h = artifacts_24h_result.scalar() or 0

    # Last 24h: audit blocks
    blocks_24h_result = await db.execute(
        select(func.count())
        .select_from(AuditEventModel)
        .where(
            AuditEventModel.timestamp >= day_ago,
            AuditEventModel.policy_decision == "blocked",
        )
    )
    blocks_24h = blocks_24h_result.scalar() or 0

    # Hallucination caught rate: audit blocks / total audit events
    total_audits_result = await db.execute(
        select(func.count()).select_from(AuditEventModel)
    )
    total_audits = total_audits_result.scalar() or 0
    total_blocks_result = await db.execute(
        select(func.count())
        .select_from(AuditEventModel)
        .where(AuditEventModel.policy_decision == "blocked")
    )
    total_blocks = total_blocks_result.scalar() or 0
    hallucination_rate = total_blocks / total_audits if total_audits > 0 else 0.0

    # Median tip-to-dossier: time from case creation to first case pack
    timing_query = await db.execute(
        select(
            func.extract(
                "epoch",
                CasePackModel.generated_at - CaseModel.created_at,
            )
        )
        .join(CaseModel, CasePackModel.case_id == CaseModel.case_id)
        .order_by(
            func.extract(
                "epoch",
                CasePackModel.generated_at - CaseModel.created_at,
            )
        )
    )
    durations = [row[0] for row in timing_query.all() if row[0] is not None and row[0] >= 0]
    median_seconds = 0.0
    if durations:
        mid = len(durations) // 2
        median_seconds = (
            durations[mid]
            if len(durations) % 2
            else (durations[mid - 1] + durations[mid]) / 2
        )

    # Entity resolution coverage: resolved mentions / total mentions
    total_mentions_result = await db.execute(
        select(func.count()).select_from(EntityMentionModel)
    )
    total_mentions = total_mentions_result.scalar() or 0
    resolved_mentions_result = await db.execute(
        select(func.count())
        .select_from(EntityMentionModel)
        .where(EntityMentionModel.resolved_entity_id.is_not(None))
    )
    resolved_mentions = resolved_mentions_result.scalar() or 0
    entity_coverage = resolved_mentions / total_mentions if total_mentions > 0 else 0.0

    logger.info(
        "metrics_served",
        case_id=None,
        source="api",
        stage="metrics",
        policy_decision="served",
        artifact_id=None,
    )

    return PublicMetrics(
        audited_dossier_pass_rate=round(pass_rate, 4),
        hallucination_caught_rate=round(hallucination_rate, 4),
        median_tip_to_dossier_seconds=round(median_seconds, 2),
        entity_resolution_coverage=round(entity_coverage, 4),
        total_cases_processed=total_cases,
        total_artifacts_ingested=total_artifacts,
        sources_active=sources_active,
        last_24h=Last24hMetrics(
            cases_created=cases_24h,
            artifacts_fetched=artifacts_24h,
            audit_blocks=blocks_24h,
        ),
    )
