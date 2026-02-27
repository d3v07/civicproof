"""Evidence Retrieval Agent.

Checks existing artifacts in the evidence store for a resolved entity,
identifies gaps in coverage across data sources, and triggers fresh
fetches for stale or missing data via connector calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from civicproof_common.db.models import RawArtifactModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Maximum artifact age before triggering a refresh
STALENESS_THRESHOLD = timedelta(days=30)

# Expected data sources for a complete investigation
EXPECTED_SOURCES = ["usaspending", "doj", "sec_edgar", "oversight_gov"]


@dataclass
class ArtifactManifest:
    """Summary of artifacts available for an entity."""

    entity_id: str
    total_artifacts: int = 0
    artifacts_by_source: dict[str, int] = field(default_factory=dict)
    stale_sources: list[str] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    freshness: dict[str, datetime | None] = field(default_factory=dict)
    coverage_score: float = 0.0


@dataclass
class EvidenceRetrievalResult:
    """Result from the evidence retrieval agent."""

    manifest: ArtifactManifest
    fetches_triggered: list[dict[str, Any]] = field(default_factory=list)
    retrieval_log: list[dict[str, Any]] = field(default_factory=list)


class EvidenceRetrievalAgent:
    """Retrieves and audits evidence availability for a case entity.

    This agent is READ-only — it inspects the artifact store but
    cannot delete or modify existing artifacts (tool scoping).
    """

    def __init__(
        self,
        db: AsyncSession,
        staleness_threshold: timedelta = STALENESS_THRESHOLD,
    ) -> None:
        self._db = db
        self._staleness = staleness_threshold

    async def retrieve(
        self,
        entity_id: str,
        entity_name: str,
        entity_uei: str | None = None,
    ) -> EvidenceRetrievalResult:
        """Check existing artifacts and identify gaps.

        Args:
            entity_id: The resolved entity ID.
            entity_name: Canonical entity name for searching.
            entity_uei: Optional UEI for narrower search.

        Returns:
            EvidenceRetrievalResult with manifest and gap analysis.
        """
        manifest = ArtifactManifest(entity_id=entity_id)

        # Query existing artifacts related to this entity
        artifacts = await self._query_artifacts(entity_name, entity_uei)

        # Build manifest
        for art in artifacts:
            source = art.source
            manifest.total_artifacts += 1
            manifest.artifacts_by_source[source] = (
                manifest.artifacts_by_source.get(source, 0) + 1
            )
            manifest.artifact_ids.append(art.artifact_id)

            # Track freshness
            if source not in manifest.freshness or (
                art.retrieved_at
                and (
                    manifest.freshness[source] is None
                    or art.retrieved_at > manifest.freshness[source]  # type: ignore[operator]
                )
            ):
                manifest.freshness[source] = art.retrieved_at

        # Identify stale and missing sources
        now = datetime.now(UTC)
        for source in EXPECTED_SOURCES:
            if source not in manifest.artifacts_by_source:
                manifest.missing_sources.append(source)
            elif manifest.freshness.get(source) is not None:
                age = now - manifest.freshness[source]  # type: ignore[operator]
                if age > self._staleness:
                    manifest.stale_sources.append(source)

        # Compute coverage score (0.0 - 1.0)
        covered = len(manifest.artifacts_by_source)
        expected = len(EXPECTED_SOURCES)
        staleness_penalty = len(manifest.stale_sources) * 0.1
        manifest.coverage_score = max(
            0.0, (covered / expected) - staleness_penalty
        )

        result = EvidenceRetrievalResult(manifest=manifest)

        # Log gaps
        if manifest.missing_sources:
            result.retrieval_log.append({
                "action": "gap_identified",
                "missing_sources": manifest.missing_sources,
                "entity": entity_name,
            })

        if manifest.stale_sources:
            result.retrieval_log.append({
                "action": "staleness_detected",
                "stale_sources": manifest.stale_sources,
                "threshold_days": self._staleness.days,
            })

        return result

    async def _query_artifacts(
        self, entity_name: str, entity_uei: str | None = None,
    ) -> list[RawArtifactModel]:
        """Query artifacts related to an entity by name or UEI."""
        from sqlalchemy import or_

        conditions = []

        # Search by name in source_url or metadata
        if entity_name:
            name_lower = entity_name.lower()
            conditions.append(
                RawArtifactModel.source_url.ilike(f"%{name_lower}%")
            )

        if not conditions:
            return []

        stmt = (
            select(RawArtifactModel)
            .where(or_(*conditions))
            .order_by(RawArtifactModel.retrieved_at.desc())
            .limit(500)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars())
