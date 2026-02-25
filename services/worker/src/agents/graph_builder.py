"""Graph Builder Agent.

Extends the evidence graph for entities involved in a case by creating
relationships from parsed data and computing centrality metrics.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from civicproof_common.db.models import (
    EntityMentionModel,
    EntityModel,
    RawArtifactModel,
    RelationshipModel,
)

logger = logging.getLogger(__name__)


@dataclass
class GraphBuildResult:
    """Result from graph builder agent."""

    nodes_added: int = 0
    edges_added: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    centrality_scores: dict[str, float] = field(default_factory=dict)
    build_log: list[dict[str, Any]] = field(default_factory=list)


class GraphBuilderAgent:
    """Builds and extends the evidence graph for case entities."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def build(
        self,
        entity_ids: list[str],
        artifact_ids: list[str],
    ) -> GraphBuildResult:
        """Build graph from co-occurring entity mentions in shared artifacts.

        Args:
            entity_ids: Entity IDs involved in the case.
            artifact_ids: Artifact IDs containing evidence.

        Returns:
            GraphBuildResult with graph statistics and centrality.
        """
        result = GraphBuildResult()

        # Find all entity mentions in the relevant artifacts
        mentions_by_artifact = await self._get_mentions_by_artifact(artifact_ids)

        # Create relationships from co-occurrence
        for artifact_id, mentions in mentions_by_artifact.items():
            entity_pairs = self._generate_pairs(mentions)
            for source_id, target_id, mention_text in entity_pairs:
                created = await self._create_relationship(
                    source_id, target_id, artifact_id, mention_text
                )
                if created:
                    result.edges_added += 1

        # Compute basic centrality (degree centrality)
        result.centrality_scores = await self._compute_degree_centrality(entity_ids)

        # Count totals
        result.total_nodes = len(entity_ids)
        result.total_edges = await self._count_edges(entity_ids)

        result.build_log.append({
            "action": "graph_built",
            "nodes_added": result.nodes_added,
            "edges_added": result.edges_added,
            "total_nodes": result.total_nodes,
            "total_edges": result.total_edges,
        })

        return result

    async def _get_mentions_by_artifact(
        self, artifact_ids: list[str]
    ) -> dict[str, list[EntityMentionModel]]:
        """Get entity mentions grouped by artifact."""
        if not artifact_ids:
            return {}

        stmt = (
            select(EntityMentionModel)
            .where(EntityMentionModel.source_artifact_id.in_(artifact_ids))
        )
        result = await self._db.execute(stmt)

        mentions_by_artifact: dict[str, list[EntityMentionModel]] = {}
        for mention in result.scalars():
            mentions_by_artifact.setdefault(
                mention.source_artifact_id, []
            ).append(mention)

        return mentions_by_artifact

    @staticmethod
    def _sanitize_mention_text(text: str) -> str:
        """Strip PII patterns from mention text before storing in metadata."""
        import re

        sanitized = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[SSN_REDACTED]", text)
        sanitized = re.sub(
            r"\b(?:\+?1[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}\b",
            "[PHONE_REDACTED]",
            sanitized,
        )
        sanitized = re.sub(
            r"\b[A-Za-z0-9._%+-]+@(?:gmail|yahoo|hotmail|outlook|aol|icloud|protonmail)\.\w+\b",
            "[EMAIL_REDACTED]",
            sanitized,
            flags=re.IGNORECASE,
        )
        return sanitized

    @staticmethod
    def _generate_pairs(
        mentions: list[EntityMentionModel],
    ) -> list[tuple[str, str, str]]:
        """Generate entity pairs from co-occurring mentions."""
        pairs = []
        resolved = [m for m in mentions if m.resolved_entity_id]
        seen = set()

        for i, m1 in enumerate(resolved):
            for m2 in resolved[i + 1 :]:
                if m1.resolved_entity_id == m2.resolved_entity_id:
                    continue
                pair_key = tuple(sorted([m1.resolved_entity_id, m2.resolved_entity_id]))
                if pair_key not in seen:
                    seen.add(pair_key)
                    context = f"{m1.raw_text} <-> {m2.raw_text}"
                    pairs.append((
                        pair_key[0],
                        pair_key[1],
                        GraphBuilderAgent._sanitize_mention_text(context),
                    ))

        return pairs

    async def _create_relationship(
        self,
        source_id: str,
        target_id: str,
        artifact_id: str,
        context: str,
    ) -> bool:
        """Create a relationship if it doesn't already exist."""
        from sqlalchemy import and_

        # Check existing
        stmt = select(RelationshipModel).where(
            and_(
                RelationshipModel.source_entity_id == source_id,
                RelationshipModel.target_entity_id == target_id,
            )
        )
        result = await self._db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update confidence if this is additional provenance
            existing.confidence = min(1.0, (existing.confidence or 0.5) + 0.1)
            return False

        rel = RelationshipModel(
            relationship_id=str(uuid.uuid4()),
            source_entity_id=source_id,
            target_entity_id=target_id,
            rel_type="affiliated_with",
            confidence=0.6,
            provenance_artifact_id=artifact_id,
            metadata_={"co_occurrence_context": context[:500]},
        )
        self._db.add(rel)
        await self._db.flush()
        return True

    async def _compute_degree_centrality(
        self, entity_ids: list[str]
    ) -> dict[str, float]:
        """Compute degree centrality for entities."""
        from sqlalchemy import or_, func

        centrality = {}
        for eid in entity_ids:
            stmt = select(func.count()).where(
                or_(
                    RelationshipModel.source_entity_id == eid,
                    RelationshipModel.target_entity_id == eid,
                )
            )
            result = await self._db.execute(stmt)
            degree = result.scalar() or 0
            # Normalize by total entity count
            centrality[eid] = degree / max(len(entity_ids), 1)

        return centrality

    async def _count_edges(self, entity_ids: list[str]) -> int:
        """Count total edges between the given entities."""
        if not entity_ids:
            return 0
        from sqlalchemy import func

        stmt = select(func.count()).where(
            RelationshipModel.source_entity_id.in_(entity_ids),
            RelationshipModel.target_entity_id.in_(entity_ids),
        )
        result = await self._db.execute(stmt)
        return result.scalar() or 0
