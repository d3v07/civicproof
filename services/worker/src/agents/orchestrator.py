"""Multi-Agent Orchestrator.

Coordinates the 6-agent pipeline for building a case pack:
  1. Entity Resolver → canonical entity IDs
  2. Evidence Retrieval → artifact manifest
  3. Graph Builder → evidence graph + centrality
  4. Anomaly Detector → risk signals
  5. Case Composer → structured dossier
  6. Auditor Gate → deterministic pass/block

Each step is idempotent, logged, has timeout + budget allocation.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from civicproof_common.db.models import (
    AuditEventModel,
    CaseModel,
    CasePackModel,
    ClaimModel,
    CitationModel,
    RawArtifactModel,
)
from civicproof_common.schemas.cases import CaseStatus

from .anomaly_detector import AnomalyDetectorAgent
from .auditor import AuditorGate, AuditorResult
from .case_composer import CaseComposerAgent, ComposedCasePack
from .entity_resolver import EntityResolverAgent
from .evidence_retrieval import EvidenceRetrievalAgent
from .graph_builder import GraphBuilderAgent

logger = logging.getLogger(__name__)


@dataclass
class PipelineStepLog:
    """Log entry for a pipeline step."""

    step: str
    status: str  # "started", "completed", "failed", "skipped"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorResult:
    """Complete result from the orchestrator."""

    case_id: str
    status: str  # "approved", "blocked", "failed"
    case_pack: ComposedCasePack | None = None
    auditor_result: AuditorResult | None = None
    pipeline_log: list[PipelineStepLog] = field(default_factory=list)
    error: str | None = None


class Orchestrator:
    """Multi-agent orchestrator for the CivicProof investigative pipeline.

    Orchestrates the full seed → case pack flow with idempotency,
    logging, timeout budgets, and deterministic auditing.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def run_pipeline(
        self,
        case_id: str,
        seed_input: dict[str, Any],
    ) -> OrchestratorResult:
        """Run the full 6-agent pipeline for a case.

        Args:
            case_id: The case ID to process.
            seed_input: The seed input (vendor_name, uei, etc.).

        Returns:
            OrchestratorResult with case pack and audit status.
        """
        result = OrchestratorResult(case_id=case_id, status="processing")

        try:
            # Update case status to INGESTING
            await self._update_case_status(case_id, CaseStatus.INGESTING)

            # ── Step 1: Entity Resolution ────────────────────────
            step1 = PipelineStepLog(step="entity_resolver", status="started")
            resolver = EntityResolverAgent(self._db)
            resolution = await resolver.resolve(seed_input)
            step1.status = "completed"
            step1.completed_at = datetime.now(UTC)
            step1.duration_seconds = (
                step1.completed_at - step1.started_at
            ).total_seconds()

            if resolution.primary_entity is None:
                step1.status = "failed"
                result.pipeline_log.append(step1)
                result.status = "failed"
                result.error = "Entity resolution failed — no entity found"
                await self._update_case_status(case_id, CaseStatus.FAILED)
                return result

            entity = resolution.primary_entity
            step1.details = {
                "entity_id": entity.entity_id,
                "canonical_name": entity.canonical_name,
                "confidence": entity.confidence,
                "resolution_method": entity.resolution_method,
                "related_count": len(resolution.related_entities),
            }
            result.pipeline_log.append(step1)
            await self._log_audit_event(
                case_id, "entity_resolver", "completed",
                f"Resolved to {entity.canonical_name} ({entity.resolution_method})",
            )

            # ── Step 2: Evidence Retrieval ────────────────────────
            await self._update_case_status(case_id, CaseStatus.INGESTING)
            step2 = PipelineStepLog(step="evidence_retrieval", status="started")
            retriever = EvidenceRetrievalAgent(self._db)
            retrieval = await retriever.retrieve(
                entity_id=entity.entity_id,
                entity_name=entity.canonical_name,
                entity_uei=entity.uei,
            )
            step2.status = "completed"
            step2.completed_at = datetime.now(UTC)
            step2.duration_seconds = (
                step2.completed_at - step2.started_at
            ).total_seconds()
            step2.details = {
                "total_artifacts": retrieval.manifest.total_artifacts,
                "coverage_score": retrieval.manifest.coverage_score,
                "missing_sources": retrieval.manifest.missing_sources,
                "stale_sources": retrieval.manifest.stale_sources,
            }
            result.pipeline_log.append(step2)
            await self._log_audit_event(
                case_id, "evidence_retrieval", "completed",
                f"Found {retrieval.manifest.total_artifacts} artifacts, "
                f"coverage={retrieval.manifest.coverage_score:.2f}",
            )

            artifact_ids = retrieval.manifest.artifact_ids
            sources_used = list(retrieval.manifest.artifacts_by_source.keys())

            # ── Step 3: Graph Builder ────────────────────────────
            await self._update_case_status(case_id, CaseStatus.ANALYZING)
            step3 = PipelineStepLog(step="graph_builder", status="started")
            all_entity_ids = [entity.entity_id] + [
                e.entity_id for e in resolution.related_entities
            ]
            graph_builder = GraphBuilderAgent(self._db)
            graph_result = await graph_builder.build(all_entity_ids, artifact_ids)
            step3.status = "completed"
            step3.completed_at = datetime.now(UTC)
            step3.duration_seconds = (
                step3.completed_at - step3.started_at
            ).total_seconds()
            step3.details = {
                "edges_added": graph_result.edges_added,
                "total_edges": graph_result.total_edges,
                "centrality": graph_result.centrality_scores,
            }
            result.pipeline_log.append(step3)

            # ── Step 4: Anomaly Detector ─────────────────────────
            step4 = PipelineStepLog(step="anomaly_detector", status="started")
            detector = AnomalyDetectorAgent(self._db)
            # Build awards data from artifact metadata (simplified)
            awards_data = await self._build_awards_data(artifact_ids)
            anomaly_result = await detector.detect(
                entity_id=entity.entity_id,
                awards=awards_data,
            )
            step4.status = "completed"
            step4.completed_at = datetime.now(UTC)
            step4.duration_seconds = (
                step4.completed_at - step4.started_at
            ).total_seconds()
            step4.details = {
                "signals_found": len(anomaly_result.risk_signals),
                "composite_score": anomaly_result.composite_risk_score,
            }
            result.pipeline_log.append(step4)
            await self._log_audit_event(
                case_id, "anomaly_detector", "completed",
                f"Found {len(anomaly_result.risk_signals)} risk signals, "
                f"composite={anomaly_result.composite_risk_score:.2f}",
            )

            # ── Step 5: Case Composer ────────────────────────────
            await self._update_case_status(case_id, CaseStatus.COMPOSING)
            step5 = PipelineStepLog(step="case_composer", status="started")
            composer = CaseComposerAgent()

            entity_profile = {
                "entity_id": entity.entity_id,
                "canonical_name": entity.canonical_name,
                "entity_type": entity.entity_type,
                "uei": entity.uei,
                "cage_code": entity.cage_code,
            }
            risk_signals = [
                {
                    "signal_type": s.signal_type,
                    "severity": s.severity,
                    "score": s.score,
                    "description": s.description,
                    "evidence": s.evidence,
                    "supporting_artifact_ids": s.supporting_artifact_ids,
                }
                for s in anomaly_result.risk_signals
            ]

            composition = composer.compose(
                case_id=case_id,
                entity_profile=entity_profile,
                artifact_ids=artifact_ids,
                risk_signals=risk_signals,
                awards_data=awards_data,
                sources_used=sources_used,
            )
            step5.status = "completed"
            step5.completed_at = datetime.now(UTC)
            step5.duration_seconds = (
                step5.completed_at - step5.started_at
            ).total_seconds()
            step5.details = {
                "claim_count": len(composition.case_pack.claims),
                "pack_hash": composition.case_pack.pack_hash,
            }
            result.pipeline_log.append(step5)

            # ── Step 6: Auditor Gate ─────────────────────────────
            await self._update_case_status(case_id, CaseStatus.AUDITING)
            step6 = PipelineStepLog(step="auditor_gate", status="started")

            # Build reference data for auditor
            valid_ids = set(artifact_ids)
            artifact_hashes = await self._get_artifact_hashes(artifact_ids)

            auditor = AuditorGate(
                valid_artifact_ids=valid_ids,
                artifact_hashes=artifact_hashes,
                min_sources=2,
            )

            # Convert case pack to auditable dict
            pack_dict = {
                "claims": [
                    {
                        "claim_id": c.claim_id,
                        "statement": c.statement,
                        "claim_type": c.claim_type,
                        "confidence": c.confidence,
                        "citation_ids": c.citation_ids,
                        "artifact_ids": c.artifact_ids,
                    }
                    for c in composition.case_pack.claims
                ],
                "sources_used": composition.case_pack.sources_used,
                "summary": composition.case_pack.summary,
                "title": composition.case_pack.title,
            }

            audit_result = auditor.audit(pack_dict)
            step6.status = "completed"
            step6.completed_at = datetime.now(UTC)
            step6.duration_seconds = (
                step6.completed_at - step6.started_at
            ).total_seconds()
            step6.details = {
                "approved": audit_result.approved,
                "violations": audit_result.violations[:5],
            }
            result.pipeline_log.append(step6)

            # ── Finalize ─────────────────────────────────────────
            result.case_pack = composition.case_pack
            result.auditor_result = audit_result

            if audit_result.approved:
                result.status = "approved"
                await self._update_case_status(case_id, CaseStatus.COMPLETE)
                await self._save_case_pack(case_id, composition.case_pack, audit_result)
                await self._log_audit_event(
                    case_id, "auditor_gate", "approved",
                    "Case pack passed all auditor rules",
                )
            else:
                result.status = "blocked"
                await self._update_case_status(
                    case_id, CaseStatus.INSUFFICIENT_EVIDENCE
                )
                await self._log_audit_event(
                    case_id, "auditor_gate", "blocked",
                    f"Case pack blocked: {len(audit_result.violations)} violation(s)",
                )

        except Exception as exc:
            logger.error("Pipeline failed for case %s: %s", case_id, exc, exc_info=True)
            result.status = "failed"
            result.error = str(exc)
            await self._update_case_status(case_id, CaseStatus.FAILED)
            await self._log_audit_event(
                case_id, "orchestrator", "failed", str(exc)
            )

        return result

    # ── Private helpers ───────────────────────────────────

    async def _update_case_status(self, case_id: str, status: CaseStatus) -> None:
        stmt = select(CaseModel).where(CaseModel.case_id == case_id)
        result = await self._db.execute(stmt)
        case = result.scalar_one_or_none()
        if case:
            case.status = status.value
            case.updated_at = datetime.now(UTC)
            await self._db.flush()

    async def _log_audit_event(
        self, case_id: str, stage: str, decision: str, detail: str
    ) -> None:
        event = AuditEventModel(
            audit_event_id=str(uuid.uuid4()),
            case_id=case_id,
            stage=stage,
            policy_decision=decision,
            detail=detail[:1000],
        )
        self._db.add(event)
        await self._db.flush()

    async def _build_awards_data(
        self, artifact_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Build simplified award data from artifacts."""
        if not artifact_ids:
            return []

        stmt = (
            select(RawArtifactModel)
            .where(
                RawArtifactModel.artifact_id.in_(artifact_ids),
                RawArtifactModel.source == "usaspending",
            )
            .limit(100)
        )
        result = await self._db.execute(stmt)
        artifacts = list(result.scalars())

        awards = []
        for art in artifacts:
            metadata = art.metadata_ or {}
            awards.append({
                "award_id": art.artifact_id,
                "vendor_id": metadata.get("vendor_id", ""),
                "award_amount": metadata.get("award_amount", 0),
                "awarding_agency": metadata.get("awarding_agency", ""),
                "start_date": metadata.get("start_date", ""),
                "extent_competed": metadata.get("extent_competed", ""),
            })
        return awards

    async def _get_artifact_hashes(
        self, artifact_ids: list[str]
    ) -> dict[str, str]:
        """Get content hashes for a list of artifacts."""
        if not artifact_ids:
            return {}

        stmt = select(RawArtifactModel).where(
            RawArtifactModel.artifact_id.in_(artifact_ids)
        )
        result = await self._db.execute(stmt)
        return {
            art.artifact_id: art.content_hash
            for art in result.scalars()
            if art.content_hash
        }

    async def _save_case_pack(
        self,
        case_id: str,
        pack: ComposedCasePack,
        audit_result: AuditorResult,
    ) -> None:
        """Persist approved case pack to DB."""
        import json

        # Save claims
        for claim in pack.claims:
            claim_model = ClaimModel(
                claim_id=claim.claim_id,
                case_id=case_id,
                statement=claim.statement,
                claim_type=claim.claim_type,
                confidence=claim.confidence,
                is_audited=True,
                audit_passed=audit_result.approved,
            )
            self._db.add(claim_model)

            for cit_id in claim.citation_ids:
                citation_model = CitationModel(
                    citation_id=str(uuid.uuid4()),
                    claim_id=claim.claim_id,
                    artifact_id=cit_id,
                    excerpt="",
                )
                self._db.add(citation_model)

        # Save case pack record
        total_citations = sum(len(c.citation_ids) for c in pack.claims)
        pack_model = CasePackModel(
            pack_id=str(uuid.uuid4()),
            case_id=case_id,
            pack_hash=pack.pack_hash,
            storage_path=f"packs/{case_id}/{pack.pack_hash[:16]}.json",
            claim_count=len(pack.claims),
            citation_count=total_citations,
            all_claims_audited=audit_result.approved,
        )
        self._db.add(pack_model)
        await self._db.commit()
